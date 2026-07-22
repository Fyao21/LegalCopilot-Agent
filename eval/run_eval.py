from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import AgentRun, AgentRunCitation, LegalArticle  # noqa: E402
from app.services.case_analyzer import analyze_case  # noqa: E402
from app.services.embedding_provider import (  # noqa: E402
    EmbeddingProvider,
    EmbeddingProviderError,
    HashEmbeddingProvider,
    get_embedding_provider,
)
from app.services.embeddings import cosine_similarity  # noqa: E402
from app.services.mixed_retriever import _keyword_score, retrieve_articles_mixed  # noqa: E402
from app.services.seed import seed_sample_laws  # noqa: E402
from app.workflows import execute_agent_run  # noqa: E402
from eval.metrics import (  # noqa: E402
    EvalCase,
    aggregate_retrieval,
    hit_at_k,
    keyword_coverage,
    load_dataset,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

Ranker = Callable[[EvalCase], list[int]]


def _keyword_ranker(db: Session, limit: int) -> Ranker:
    articles = list(db.scalars(select(LegalArticle)).all())

    def rank(case: EvalCase) -> list[int]:
        query = f"{case.case_text}\n{case.question}"
        scored = sorted(articles, key=lambda article: _keyword_score(query, article), reverse=True)
        return [article.id for article in scored[:limit]]

    return rank


def _semantic_ranker(db: Session, provider: EmbeddingProvider, limit: int) -> Ranker:
    articles = list(db.scalars(select(LegalArticle)).all())
    vectors = provider.embed_documents(
        [f"{article.law_name}{article.article_number}{article.content}" for article in articles]
    )

    def rank(case: EvalCase) -> list[int]:
        query_vector = provider.embed_query(f"{case.case_text}\n{case.question}")
        scored = sorted(
            zip(articles, vectors, strict=True),
            key=lambda item: cosine_similarity(query_vector, item[1]),
            reverse=True,
        )
        return [article.id for article, _ in scored[:limit]]

    return rank


def _mixed_ranker(db: Session, provider: EmbeddingProvider, limit: int) -> Ranker:
    def rank(case: EvalCase) -> list[int]:
        query = f"{case.case_text}\n{case.question}"
        result = retrieve_articles_mixed(db, query, provider, limit)
        return [citation.article_id for citation in result.citations]

    return rank


def _evaluate_retriever(name: str, cases: list[EvalCase], ranker: Ranker) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for case in cases:
        started = time.perf_counter()
        ranked_ids = ranker(case)
        latency_ms = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "case_id": case.case_id,
                "ranked_article_ids": ranked_ids,
                "relevant_article_ids": case.relevant_article_ids,
                "recall_at_5": recall_at_k(ranked_ids, case.relevant_article_ids, 5),
                "mrr": reciprocal_rank(ranked_ids, case.relevant_article_ids),
                "hit_at_1": hit_at_k(ranked_ids, case.relevant_article_ids, 1),
                "hit_at_3": hit_at_k(ranked_ids, case.relevant_article_ids, 3),
                "hit_at_5": hit_at_k(ranked_ids, case.relevant_article_ids, 5),
                "precision_at_5": precision_at_k(ranked_ids, case.relevant_article_ids, 5),
                "latency_ms": round(latency_ms, 3),
            }
        )
    return {"name": name, "status": "completed", "metrics": aggregate_retrieval(rows), "cases": rows}


def _evaluate_extraction(cases: list[EvalCase]) -> dict[str, float]:
    type_scores: list[float] = []
    fact_scores: list[float] = []
    focus_scores: list[float] = []
    for case in cases:
        facts = analyze_case(case.case_text, case.question)
        type_scores.append(float(facts.case_type == case.expected_case_type))
        fact_scores.append(keyword_coverage(case.key_fact_keywords, " ".join(facts.key_facts)))
        focus_scores.append(keyword_coverage(case.dispute_focus_keywords, " ".join(facts.dispute_focuses)))
    return {
        "case_type_accuracy": round(mean(type_scores), 4),
        "key_fact_keyword_coverage": round(mean(fact_scores), 4),
        "dispute_focus_keyword_coverage": round(mean(focus_scores), 4),
    }


def _evaluate_system(db: Session, cases: list[EvalCase]) -> dict[str, float | int]:
    durations: list[float] = []
    successes = 0
    verified = 0
    citations = 0
    review_nodes = 0
    for case in cases:
        run = AgentRun(question=case.question, extracted_text=case.case_text, mode="offline")
        db.add(run)
        db.commit()
        db.refresh(run)
        started = time.perf_counter()
        execute_agent_run(db, run)
        durations.append((time.perf_counter() - started) * 1000)
        successes += int(run.status == "completed")
        stored = run.node_traces or []
        review_nodes += sum("引用审核完成" in str(trace.get("action_summary", "")) for trace in stored)
        citation_rows = list(
            db.scalars(select(AgentRunCitation).where(AgentRunCitation.run_id == run.id)).all()
        )
        citations += len(citation_rows)
        verified += sum(citation.verified for citation in citation_rows)
    ordered = sorted(durations)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
    return {
        "workflow_success_rate": round(successes / len(cases), 4),
        "citation_integrity_rate": round(verified / citations, 4) if citations else 0.0,
        "average_latency_ms": round(mean(durations), 3),
        "p95_latency_ms": round(ordered[p95_index], 3),
        "model_api_calls": 0,
        "estimated_model_cost_cny": 0.0,
        "completed_review_nodes": review_nodes,
    }


def _markdown_summary(result: dict[str, Any]) -> str:
    extraction = result["extraction"]
    system = result["system"]
    lines = [
        "# 第四周评测结果",
        "",
        f"- 数据集：{result['dataset_size']} 条脱敏教学样例",
        f"- 生成时间：{result['generated_at']}",
        f"- 案件类型准确率：{extraction['case_type_accuracy']:.2%}",
        f"- 工作流成功率：{system['workflow_success_rate']:.2%}",
        "",
        "## 检索对照",
        "",
        "| 方案 | 状态 | Recall@5 | MRR | Hit@1 | 平均耗时(ms) | P95(ms) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for method in result["retrieval"]:
        if method["status"] != "completed":
            lines.append(f"| {method['name']} | {method['status']} | - | - | - | - | - |")
            continue
        metrics = method["metrics"]
        lines.append(
            f"| {method['name']} | completed | {metrics['recall_at_5']:.4f} | {metrics['mrr']:.4f} | "
            f"{metrics['hit_at_1']:.4f} | {metrics['average_latency_ms']:.3f} | {metrics['p95_latency_ms']:.3f} |"
        )
    lines.extend(
        [
            "",
            "> 在线 Embedding 组只有在显式传入 `--include-online` 且配置独立 Embedding 服务时才运行。",
            "> 当前样例法规仅用于工程评测，不代表真实法律服务效果。",
            "",
        ]
    )
    return "\n".join(lines)


def run(dataset_path: Path, include_online: bool) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_sample_laws(db)
        retrieval: list[dict[str, Any]] = [
            _evaluate_retriever("keyword", cases, _keyword_ranker(db, 5)),
            _evaluate_retriever("hash_semantic", cases, _semantic_ranker(db, HashEmbeddingProvider(), 5)),
            _evaluate_retriever("hash_mixed", cases, _mixed_ranker(db, HashEmbeddingProvider(), 5)),
        ]
        if include_online:
            try:
                provider = get_embedding_provider(force_offline=False)
                if provider.provider_name == "hash":
                    raise EmbeddingProviderError("EMBEDDING_PROVIDER 仍为 hash")
                retrieval.append(
                    _evaluate_retriever(
                        f"online_mixed:{provider.model_name}",
                        cases,
                        _mixed_ranker(db, provider, 5),
                    )
                )
            except EmbeddingProviderError as error:
                retrieval.append({"name": "online_mixed", "status": "skipped", "reason": str(error)})
        else:
            retrieval.append(
                {
                    "name": "online_mixed",
                    "status": "skipped",
                    "reason": "未传入 --include-online，避免评测意外产生外部调用和费用",
                }
            )
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset_path": dataset_path.relative_to(PROJECT_ROOT).as_posix(),
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "dataset_size": len(cases),
            "environment": {
                "workflow_mode": "offline",
                "configured_offline_mode": get_settings().offline_mode,
                "top_k": 5,
                "online_embedding_requested": include_online,
                "ci": os.getenv("CI", "").lower() == "true",
            },
            "extraction": _evaluate_extraction(cases),
            "retrieval": retrieval,
            "system": _evaluate_system(db, cases),
            "limitations": [
                "关键事实和争议焦点采用关键词覆盖率，不等同于人工语义评分。",
                "24 条数据为项目作者构造的脱敏教学样例，规模不足以代表生产效果。",
                "在线 Embedding 指标只有在独立服务已配置并显式启用时才生成。",
            ],
        }
    engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="运行律镜离线评测与检索对照实验")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "eval" / "dataset.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "eval" / "results" / "latest.json")
    parser.add_argument("--include-online", action="store_true")
    args = parser.parse_args()
    result = run(args.dataset.resolve(), args.include_online)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_markdown_summary(result), encoding="utf-8")
    print(
        json.dumps({"output": str(args.output), "dataset_size": result["dataset_size"]}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
