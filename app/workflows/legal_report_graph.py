from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import get_llm_client
from app.models import AgentRun, AgentRunCitation
from app.schemas import CaseFacts, Citation, NodeTrace, ReviewedCitation
from app.services.case_agent import analyze_case_agent
from app.services.citation_reviewer import review_citations
from app.services.embedding_provider import get_embedding_provider
from app.services.mixed_retriever import retrieve_articles_mixed
from app.services.report_writer import create_report_draft, render_markdown


class WorkflowState(TypedDict, total=False):
    run_id: int
    document_text: str
    question: str
    mode: str
    facts: CaseFacts
    retrieval_query: str
    citations: list[Citation]
    reviewed_citations: list[ReviewedCitation]
    retry_count: int
    traces: list[NodeTrace]
    report_title: str
    report_markdown: str
    evidence_gaps: list[str]
    model_name: str | None


def _trace(node: str, started: float, summary: str, error_code: str | None = None) -> NodeTrace:
    return NodeTrace(
        node=node,
        status="failed" if error_code else "completed",
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        action_summary=summary,
        error_code=error_code,
    )


def _build_graph(db: Session, mode: str):
    llm = None if mode == "offline" else get_llm_client()
    provider = get_embedding_provider(force_offline=(mode == "offline"))
    settings = get_settings()

    def publish(
        run_id: int,
        *,
        status: str,
        node: str,
        progress: int,
        traces: list[NodeTrace] | None = None,
    ) -> None:
        current = db.get(AgentRun, run_id)
        if current is None:
            return
        current.status = status
        current.current_node = node
        current.progress = progress
        if traces is not None:
            current.node_traces = [trace.model_dump() for trace in traces]
        db.commit()

    def analyze_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="analyzing", node="analyze_case", progress=15)
        started = time.perf_counter()
        outcome = analyze_case_agent(state["document_text"], state["question"], llm)
        summary = f"案件要素提取完成，来源={outcome.source}，类型={outcome.facts.case_type}"
        if outcome.fallback_reason:
            summary += f"，回退原因={outcome.fallback_reason}"
        traces = [*state.get("traces", []), _trace("analyze_case", started, summary)]
        publish(state["run_id"], status="analyzing", node="analyze_case", progress=30, traces=traces)
        return {
            "facts": outcome.facts,
            "model_name": llm.model if llm else None,
            "traces": traces,
        }

    def retrieve_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="retrieving", node="retrieve_laws", progress=40)
        started = time.perf_counter()
        facts = state["facts"]
        query_parts = [state["question"], *facts.dispute_focuses, *facts.claims]
        if state.get("retry_count", 0):
            query_parts.extend([facts.case_type, "法律责任", "请求权基础"])
        query = "\n".join(part for part in query_parts if part)
        result = retrieve_articles_mixed(db, query, provider, get_settings().top_k)
        traces = [
            *state.get("traces", []),
            _trace(
                "retrieve_laws",
                started,
                f"混合检索完成，provider={result.provider}，候选={len(result.citations)}",
            ),
        ]
        publish(state["run_id"], status="retrieving", node="retrieve_laws", progress=55, traces=traces)
        return {
            "retrieval_query": query,
            "citations": result.citations,
            "traces": traces,
        }

    def review_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="reviewing", node="review_citations", progress=65)
        started = time.perf_counter()
        reviewed = review_citations(db, state.get("citations", []), state["retrieval_query"], llm)
        verified_count = sum(citation.verified for citation in reviewed)
        traces = [
            *state.get("traces", []),
            _trace("review_citations", started, f"引用审核完成，通过={verified_count}，总数={len(reviewed)}"),
        ]
        publish(state["run_id"], status="reviewing", node="review_citations", progress=75, traces=traces)
        return {
            "reviewed_citations": reviewed,
            "traces": traces,
        }

    def retry_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="retrieving", node="retry_retrieval", progress=50)
        started = time.perf_counter()
        retry_count = state.get("retry_count", 0) + 1
        traces = [
            *state.get("traces", []),
            _trace("retry_retrieval", started, f"准备第 {retry_count} 次补充检索"),
        ]
        publish(state["run_id"], status="retrieving", node="retry_retrieval", progress=50, traces=traces)
        return {
            "retry_count": retry_count,
            "traces": traces,
        }

    def report_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="writing", node="write_report", progress=85)
        started = time.perf_counter()
        draft, fallback_reason = create_report_draft(state["facts"], state.get("reviewed_citations", []), llm)
        markdown = render_markdown(draft, state["facts"], state.get("reviewed_citations", []))
        summary = "报告生成完成"
        if fallback_reason:
            summary += f"，使用离线回退：{fallback_reason}"
        traces = [*state.get("traces", []), _trace("write_report", started, summary)]
        publish(state["run_id"], status="writing", node="write_report", progress=95, traces=traces)
        return {
            "report_title": draft.title,
            "report_markdown": markdown,
            "evidence_gaps": draft.evidence_gaps,
            "model_name": state.get("model_name") or "offline-template",
            "traces": traces,
        }

    def after_review(state: WorkflowState) -> Literal["write_report", "retry_retrieval"]:
        if any(citation.verified for citation in state.get("reviewed_citations", [])):
            return "write_report"
        if state.get("retry_count", 0) < settings.max_workflow_retries:
            return "retry_retrieval"
        return "write_report"

    builder = StateGraph(WorkflowState)
    builder.add_node("analyze_case", analyze_node)
    builder.add_node("retrieve_laws", retrieve_node)
    builder.add_node("review_citations", review_node)
    builder.add_node("retry_retrieval", retry_node)
    builder.add_node("write_report", report_node)
    builder.add_edge(START, "analyze_case")
    builder.add_edge("analyze_case", "retrieve_laws")
    builder.add_edge("retrieve_laws", "review_citations")
    builder.add_conditional_edges(
        "review_citations",
        after_review,
        {"write_report": "write_report", "retry_retrieval": "retry_retrieval"},
    )
    builder.add_edge("retry_retrieval", "retrieve_laws")
    builder.add_edge("write_report", END)
    return builder.compile()


def execute_agent_run(db: Session, run: AgentRun) -> AgentRun:
    run.status = "analyzing"
    run.current_node = "analyze_case"
    run.progress = 10
    run.started_at = datetime.now(UTC)
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    db.commit()
    initial_state: WorkflowState = {
        "run_id": run.id,
        "document_text": run.extracted_text,
        "question": run.question,
        "mode": run.mode,
        "retry_count": 0,
        "traces": [],
    }
    try:
        result = _build_graph(db, run.mode).invoke(initial_state)
        run.status = "completed"
        run.current_node = "completed"
        run.progress = 100
        run.retry_count = result.get("retry_count", 0)
        run.facts = result["facts"].model_dump()
        run.report_title = result["report_title"]
        run.report_markdown = result["report_markdown"]
        run.evidence_gaps = result.get("evidence_gaps", [])
        run.node_traces = [trace.model_dump() for trace in result.get("traces", [])]
        run.model_name = result.get("model_name")
        run.completed_at = datetime.now(UTC)
        for citation in result.get("reviewed_citations", []):
            db.add(
                AgentRunCitation(
                    run_id=run.id,
                    article_id=citation.article_id,
                    score=citation.score,
                    keyword_score=citation.keyword_score or 0.0,
                    semantic_score=citation.semantic_score or 0.0,
                    review_status=citation.review_status,
                    review_reason=citation.review_reason,
                    verified=citation.verified,
                )
            )
    except Exception as error:
        run.status = "failed"
        run.current_node = "failed"
        run.error_code = type(error).__name__.upper()
        run.error_message = str(error)[:1000]
        run.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    return run
