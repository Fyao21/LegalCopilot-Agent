from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Literal, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import OpenAICompatibleLLM, get_llm_client
from app.models import (
    AgentApproval,
    AgentClarification,
    AgentRun,
    AgentRunCitation,
    ReportVersion,
)
from app.schemas import CaseFacts, Citation, NodeTrace, ReviewedCitation
from app.services.case_agent import analyze_case_agent
from app.services.citation_reviewer import review_citations
from app.services.monitoring import persist_span_records
from app.services.observability import observe_span
from app.services.report_writer import create_report_draft, render_markdown, revise_report_markdown
from app.services.retrieval_service import retrieve_articles_configured


class WorkflowState(TypedDict, total=False):
    run_id: int
    document_text: str
    question: str
    mode: str
    as_of_date: str | None
    facts: dict
    retrieval_query: str
    citations: list[dict]
    reviewed_citations: list[dict]
    retry_count: int
    clarification_round: int
    traces: list[dict]
    report_title: str
    report_markdown: str
    evidence_gaps: list[str]
    model_name: str | None
    report_version_number: int
    change_summary: str | None
    approval_action: str | None
    approval_comment: str | None
    observability_spans: list[dict]


_memory_savers: dict[int, MemorySaver] = {}


@contextmanager
def _open_checkpointer(db: Session) -> Iterator[BaseCheckpointSaver]:
    """Keep local SQLite checkpoints beside business data.

    In-memory unit-test databases reuse one MemorySaver per SQLAlchemy engine.
    The portfolio app uses the same SQLite file as its business tables, so a
    service restart can resume a waiting thread without creating another DB.
    """

    bind = db.get_bind()
    engine = bind.engine
    database = engine.url.database
    if bind.dialect.name == "sqlite" and database and database != ":memory:":
        connection = sqlite3.connect(database, check_same_thread=False, timeout=30)
        saver = SqliteSaver(connection)
        saver.setup()
        try:
            yield saver
        finally:
            connection.close()
        return
    key = id(engine)
    yield _memory_savers.setdefault(key, MemorySaver())


def _trace(node: str, started: float, summary: str, error_code: str | None = None) -> dict:
    return NodeTrace(
        node=node,
        status="failed" if error_code else "completed",
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        action_summary=summary,
        error_code=error_code,
    ).model_dump()


def _usage_snapshot(llm: OpenAICompatibleLLM | None) -> tuple[int, int, int]:
    if llm is None or not hasattr(llm, "usage_snapshot"):
        return (0, 0, 0)
    usage = llm.usage_snapshot()
    return (usage.input_tokens, usage.output_tokens, usage.retry_count)


def _usage_delta(
    before: tuple[int, int, int],
    after: tuple[int, int, int],
) -> tuple[int, int, int]:
    return (
        max(0, after[0] - before[0]),
        max(0, after[1] - before[1]),
        max(0, after[2] - before[2]),
    )


def _llm_last_error(llm: OpenAICompatibleLLM | None) -> str | None:
    if llm is None or not hasattr(llm, "usage_snapshot"):
        return None
    return getattr(llm.usage_snapshot(), "last_error_code", None)


def _state_as_of_date(state: WorkflowState) -> date | None:
    value = state.get("as_of_date")
    return date.fromisoformat(value) if value else None


def _clarification_questions(facts: CaseFacts, round_number: int, limit: int) -> list[dict]:
    prompts = facts.questions_for_user[:limit]
    if not prompts:
        prompts = [f"请补充说明：{field}" for field in facts.missing_information[:limit]]
    questions: list[dict] = []
    for index, prompt in enumerate(prompts):
        missing_field = facts.missing_information[index] if index < len(facts.missing_information) else None
        questions.append(
            {
                "question_id": f"r{round_number}-q{index + 1}",
                "prompt": prompt,
                "missing_field": missing_field,
                "required": True,
            }
        )
    return questions


def _build_graph(db: Session, mode: str, checkpointer: BaseCheckpointSaver):
    llm = None if mode == "offline" else get_llm_client()
    settings = get_settings()

    def publish(
        run_id: int,
        *,
        status: str,
        node: str,
        progress: int,
        traces: list[dict] | None = None,
    ) -> None:
        current = db.get(AgentRun, run_id)
        if current is None:
            return
        current.status = status
        current.current_node = node
        current.progress = progress
        if traces is not None:
            current.node_traces = traces
        db.commit()

    def analyze_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="analyzing", node="analyze_case", progress=15)
        started = time.perf_counter()
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.analyze_case",
            run_id=state["run_id"],
            node="analyze_case",
            attributes={"agent.mode": mode},
        ) as node_observation:
            if llm is not None:
                before_usage = _usage_snapshot(llm)
                with observe_span(
                    "gen_ai.chat",
                    run_id=state["run_id"],
                    node="analyze_case",
                    attributes={
                        "agent.mode": mode,
                        "gen_ai.provider.name": "openai-compatible",
                        "gen_ai.request.model": llm.model,
                    },
                ) as chat_observation:
                    outcome = analyze_case_agent(
                        state["document_text"],
                        state["question"],
                        llm,
                    )
                    input_tokens, output_tokens, llm_retries = _usage_delta(
                        before_usage,
                        _usage_snapshot(llm),
                    )
                    span_records.append(
                        chat_observation.finish(
                            provider="openai-compatible",
                            model=llm.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            retry_count=llm_retries,
                            fallback_reason=outcome.fallback_reason,
                        )
                    )
            else:
                outcome = analyze_case_agent(
                    state["document_text"],
                    state["question"],
                    llm,
                )
            summary = f"案件要素提取完成，来源={outcome.source}，类型={outcome.facts.case_type}"
            if outcome.fallback_reason:
                summary += f"，回退原因={outcome.fallback_reason}"
            span_records.append(
                node_observation.finish(
                    provider="openai-compatible" if llm else "rules",
                    model=llm.model if llm else None,
                    fallback_reason=outcome.fallback_reason,
                    attributes={"agent.status": "completed"},
                )
            )
        traces = [*state.get("traces", []), _trace("analyze_case", started, summary)]
        publish(state["run_id"], status="analyzing", node="analyze_case", progress=30, traces=traces)
        return {
            "facts": outcome.facts.model_dump(),
            "model_name": llm.model if llm else None,
            "traces": traces,
            "observability_spans": span_records,
        }

    def after_analysis(state: WorkflowState) -> Literal["clarify_user", "retrieve_laws"]:
        facts = CaseFacts.model_validate(state["facts"])
        needs_answer = bool(facts.missing_information or facts.questions_for_user)
        if needs_answer and state.get("clarification_round", 0) < settings.max_clarification_rounds:
            return "clarify_user"
        return "retrieve_laws"

    def clarify_node(state: WorkflowState) -> dict:
        facts = CaseFacts.model_validate(state["facts"])
        round_number = state.get("clarification_round", 0) + 1
        questions = _clarification_questions(
            facts,
            round_number,
            settings.max_questions_per_round,
        )
        resume_value = interrupt(
            {
                "type": "clarification",
                "round": round_number,
                "max_rounds": settings.max_clarification_rounds,
                "questions": questions,
            }
        )
        answers = resume_value.get("answers", []) if isinstance(resume_value, dict) else []
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.interrupt.resume",
            run_id=state["run_id"],
            node="clarify_user",
            attributes={"agent.mode": mode},
        ) as observation:
            answer_by_id = {
                item.get("question_id"): str(item.get("answer", "")).strip()
                for item in answers
                if isinstance(item, dict)
            }
            supplement = [
                f"问题：{question['prompt']}\n用户回答：{answer_by_id.get(question['question_id'], '暂不清楚')}"
                for question in questions
            ]
            updated_text = (
                f"{state['document_text']}\n\n[第 {round_number} 轮用户补充]\n" + "\n".join(supplement)
            ).strip()
            span_records.append(
                observation.finish(
                    attributes={"agent.status": "resumed"},
                )
            )
        traces = [
            *state.get("traces", []),
            _trace("clarify_user", time.perf_counter(), f"已合并第 {round_number} 轮用户回答"),
        ]
        publish(
            state["run_id"],
            status="resuming",
            node="clarify_user",
            progress=35,
            traces=traces,
        )
        return {
            "document_text": updated_text,
            "clarification_round": round_number,
            "traces": traces,
            "observability_spans": span_records,
        }

    def retrieve_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="retrieving", node="retrieve_laws", progress=40)
        started = time.perf_counter()
        facts = CaseFacts.model_validate(state["facts"])
        query_parts = [state["question"], *facts.dispute_focuses, *facts.claims]
        if state.get("retry_count", 0):
            query_parts.extend([facts.case_type, "法律责任", "请求权基础"])
        query = "\n".join(part for part in query_parts if part)
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.retrieval",
            run_id=state["run_id"],
            node="retrieve_laws",
            attributes={"agent.mode": mode},
        ) as retrieval_observation:
            with observe_span(
                "gen_ai.embeddings",
                run_id=state["run_id"],
                node="retrieve_laws",
                attributes={"agent.mode": mode},
            ) as embedding_observation:
                result = retrieve_articles_configured(
                    db,
                    query,
                    settings.top_k,
                    force_offline=(mode == "offline"),
                    as_of_date=_state_as_of_date(state),
                )
                span_records.append(
                    embedding_observation.finish(
                        provider=result.attempted_provider or result.provider,
                        model=result.attempted_model or result.model,
                        input_tokens=result.input_tokens,
                        retry_count=result.retry_count,
                        fallback_reason=result.fallback_reason,
                        operation="embedding",
                        attributes={"retrieval.provider": result.provider},
                    )
                )
            summary = (
                f"混合检索完成，provider={result.provider}，"
                f"适用日期={result.as_of_date.isoformat()}，候选={len(result.citations)}"
            )
            if result.fallback_reason:
                summary += f"，回退原因={result.fallback_reason}"
            span_records.append(
                retrieval_observation.finish(
                    provider=result.provider,
                    model=result.model,
                    retry_count=result.retry_count,
                    fallback_reason=result.fallback_reason,
                    attributes={
                        "retrieval.provider": result.provider,
                        "retrieval.candidate_count": len(result.citations),
                    },
                )
            )
        traces = [*state.get("traces", []), _trace("retrieve_laws", started, summary)]
        publish(state["run_id"], status="retrieving", node="retrieve_laws", progress=55, traces=traces)
        return {
            "retrieval_query": query,
            "citations": [citation.model_dump(mode="json") for citation in result.citations],
            "traces": traces,
            "observability_spans": span_records,
        }

    def review_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="reviewing", node="review_citations", progress=65)
        started = time.perf_counter()
        citations = [Citation.model_validate(item) for item in state.get("citations", [])]
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.review_citations",
            run_id=state["run_id"],
            node="review_citations",
            attributes={"agent.mode": mode},
        ) as review_observation:
            if llm is not None:
                before_usage = _usage_snapshot(llm)
                with observe_span(
                    "gen_ai.chat",
                    run_id=state["run_id"],
                    node="review_citations",
                    attributes={
                        "agent.mode": mode,
                        "gen_ai.provider.name": "openai-compatible",
                        "gen_ai.request.model": llm.model,
                    },
                ) as chat_observation:
                    reviewed = review_citations(
                        db,
                        citations,
                        state["retrieval_query"],
                        llm,
                    )
                    input_tokens, output_tokens, llm_retries = _usage_delta(
                        before_usage,
                        _usage_snapshot(llm),
                    )
                    review_fallback = _llm_last_error(llm)
                    span_records.append(
                        chat_observation.finish(
                            provider="openai-compatible",
                            model=llm.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            retry_count=llm_retries,
                            fallback_reason=review_fallback,
                        )
                    )
            else:
                reviewed = review_citations(
                    db,
                    citations,
                    state["retrieval_query"],
                    llm,
                )
                review_fallback = None
            verified_count = sum(citation.verified for citation in reviewed)
            span_records.append(
                review_observation.finish(
                    provider="openai-compatible" if llm else "database",
                    model=llm.model if llm else None,
                    fallback_reason=review_fallback,
                    attributes={"retrieval.verified_count": verified_count},
                )
            )
        traces = [
            *state.get("traces", []),
            _trace("review_citations", started, f"引用审核完成，通过={verified_count}，总数={len(reviewed)}"),
        ]
        publish(state["run_id"], status="reviewing", node="review_citations", progress=75, traces=traces)
        return {
            "reviewed_citations": [citation.model_dump(mode="json") for citation in reviewed],
            "traces": traces,
            "observability_spans": span_records,
        }

    def retry_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="retrieving", node="retry_retrieval", progress=50)
        started = time.perf_counter()
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.retry",
            run_id=state["run_id"],
            node="retry_retrieval",
            attributes={"agent.mode": mode},
        ) as observation:
            retry_count = state.get("retry_count", 0) + 1
            span_records.append(
                observation.finish(
                    retry_count=retry_count,
                    attributes={"retry.count": retry_count},
                )
            )
        traces = [
            *state.get("traces", []),
            _trace("retry_retrieval", started, f"准备第 {retry_count} 次补充检索"),
        ]
        publish(state["run_id"], status="retrieving", node="retry_retrieval", progress=50, traces=traces)
        return {
            "retry_count": retry_count,
            "traces": traces,
            "observability_spans": span_records,
        }

    def report_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="writing", node="write_report", progress=85)
        started = time.perf_counter()
        facts = CaseFacts.model_validate(state["facts"])
        citations = [ReviewedCitation.model_validate(item) for item in state.get("reviewed_citations", [])]
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.write_report",
            run_id=state["run_id"],
            node="write_report",
            attributes={"agent.mode": mode},
        ) as report_observation:
            if llm is not None:
                before_usage = _usage_snapshot(llm)
                with observe_span(
                    "gen_ai.chat",
                    run_id=state["run_id"],
                    node="write_report",
                    attributes={
                        "agent.mode": mode,
                        "gen_ai.provider.name": "openai-compatible",
                        "gen_ai.request.model": llm.model,
                    },
                ) as chat_observation:
                    draft, fallback_reason = create_report_draft(
                        facts,
                        citations,
                        llm,
                    )
                    input_tokens, output_tokens, llm_retries = _usage_delta(
                        before_usage,
                        _usage_snapshot(llm),
                    )
                    span_records.append(
                        chat_observation.finish(
                            provider="openai-compatible",
                            model=llm.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            retry_count=llm_retries,
                            fallback_reason=fallback_reason,
                        )
                    )
            else:
                draft, fallback_reason = create_report_draft(
                    facts,
                    citations,
                    llm,
                )
            markdown = render_markdown(
                draft,
                facts,
                citations,
                _state_as_of_date(state),
            )
            summary = "报告生成完成"
            if fallback_reason:
                summary += f"，使用离线回退：{fallback_reason}"
            span_records.append(
                report_observation.finish(
                    provider="openai-compatible" if llm else "offline-template",
                    model=llm.model if llm else "offline-template",
                    fallback_reason=fallback_reason,
                )
            )
        traces = [*state.get("traces", []), _trace("write_report", started, summary)]
        publish(state["run_id"], status="writing", node="write_report", progress=95, traces=traces)
        return {
            "report_title": draft.title,
            "report_markdown": markdown,
            "report_version_number": 1,
            "change_summary": "Agent 生成初始报告草稿",
            "evidence_gaps": draft.evidence_gaps,
            "model_name": state.get("model_name") or "offline-template",
            "traces": traces,
            "observability_spans": span_records,
        }

    def approval_node(state: WorkflowState) -> dict:
        version_number = state.get("report_version_number", 1)
        publish(
            state["run_id"],
            status="waiting_for_approval",
            node="approve_report",
            progress=97,
            traces=state.get("traces", []),
        )
        resume_value = interrupt(
            {
                "type": "approval",
                "report_version": version_number,
                "title": state["report_title"],
                "change_summary": state.get("change_summary"),
                "allowed_actions": ["approve", "request_changes", "reject"],
            }
        )
        action = resume_value.get("action") if isinstance(resume_value, dict) else None
        comment = resume_value.get("comment", "") if isinstance(resume_value, dict) else ""
        if action not in {"approve", "request_changes", "reject"}:
            raise RuntimeError("审批恢复指令无效")
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.approval.resume",
            run_id=state["run_id"],
            node="approve_report",
            attributes={"agent.mode": mode},
        ) as observation:
            span_records.append(
                observation.finish(
                    attributes={"agent.status": str(action)},
                )
            )
        traces = [
            *state.get("traces", []),
            _trace("approve_report", time.perf_counter(), f"人工审批动作：{action}"),
        ]
        publish(
            state["run_id"],
            status="revising" if action == "request_changes" else "resuming",
            node="approve_report",
            progress=97,
            traces=traces,
        )
        return {
            "approval_action": action,
            "approval_comment": str(comment).strip(),
            "traces": traces,
            "observability_spans": span_records,
        }

    def revise_node(state: WorkflowState) -> dict:
        publish(state["run_id"], status="revising", node="revise_report", progress=90)
        started = time.perf_counter()
        facts = CaseFacts.model_validate(state["facts"])
        citations = [ReviewedCitation.model_validate(item) for item in state.get("reviewed_citations", [])]
        next_version = state.get("report_version_number", 1) + 1
        span_records = list(state.get("observability_spans", []))
        with observe_span(
            "agent.revise_report",
            run_id=state["run_id"],
            node="revise_report",
            attributes={"agent.mode": mode},
        ) as revision_observation:
            if llm is not None:
                before_usage = _usage_snapshot(llm)
                with observe_span(
                    "gen_ai.chat",
                    run_id=state["run_id"],
                    node="revise_report",
                    attributes={
                        "agent.mode": mode,
                        "gen_ai.provider.name": "openai-compatible",
                        "gen_ai.request.model": llm.model,
                    },
                ) as chat_observation:
                    revision, fallback_reason = revise_report_markdown(
                        state["report_markdown"],
                        state.get("approval_comment") or "请复核并完善报告",
                        next_version,
                        facts,
                        citations,
                        llm,
                    )
                    input_tokens, output_tokens, llm_retries = _usage_delta(
                        before_usage,
                        _usage_snapshot(llm),
                    )
                    span_records.append(
                        chat_observation.finish(
                            provider="openai-compatible",
                            model=llm.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            retry_count=llm_retries,
                            fallback_reason=fallback_reason,
                        )
                    )
            else:
                revision, fallback_reason = revise_report_markdown(
                    state["report_markdown"],
                    state.get("approval_comment") or "请复核并完善报告",
                    next_version,
                    facts,
                    citations,
                    llm,
                )
            summary = revision.change_summary
            if fallback_reason:
                summary += f"，使用离线回退：{fallback_reason}"
            span_records.append(
                revision_observation.finish(
                    provider="openai-compatible" if llm else "offline-template",
                    model=llm.model if llm else "offline-template",
                    fallback_reason=fallback_reason,
                )
            )
        traces = [*state.get("traces", []), _trace("revise_report", started, summary)]
        publish(
            state["run_id"],
            status="revising",
            node="revise_report",
            progress=95,
            traces=traces,
        )
        return {
            "report_markdown": revision.markdown,
            "report_version_number": next_version,
            "change_summary": revision.change_summary,
            "approval_action": None,
            "approval_comment": None,
            "traces": traces,
            "observability_spans": span_records,
        }

    def after_approval(state: WorkflowState) -> Literal["revise_report", "finish"]:
        if state.get("approval_action") == "request_changes":
            return "revise_report"
        return "finish"

    def after_review(state: WorkflowState) -> Literal["write_report", "retry_retrieval"]:
        if any(item.get("verified") for item in state.get("reviewed_citations", [])):
            return "write_report"
        if state.get("retry_count", 0) < settings.max_workflow_retries:
            return "retry_retrieval"
        return "write_report"

    builder = StateGraph(WorkflowState)
    builder.add_node("analyze_case", analyze_node)
    builder.add_node("clarify_user", clarify_node)
    builder.add_node("retrieve_laws", retrieve_node)
    builder.add_node("review_citations", review_node)
    builder.add_node("retry_retrieval", retry_node)
    builder.add_node("write_report", report_node)
    builder.add_node("approve_report", approval_node)
    builder.add_node("revise_report", revise_node)
    builder.add_edge(START, "analyze_case")
    builder.add_conditional_edges(
        "analyze_case",
        after_analysis,
        {"clarify_user": "clarify_user", "retrieve_laws": "retrieve_laws"},
    )
    builder.add_edge("clarify_user", "analyze_case")
    builder.add_edge("retrieve_laws", "review_citations")
    builder.add_conditional_edges(
        "review_citations",
        after_review,
        {"write_report": "write_report", "retry_retrieval": "retry_retrieval"},
    )
    builder.add_edge("retry_retrieval", "retrieve_laws")
    builder.add_edge("write_report", "approve_report")
    builder.add_conditional_edges(
        "approve_report",
        after_approval,
        {"revise_report": "revise_report", "finish": END},
    )
    builder.add_edge("revise_report", "approve_report")
    return builder.compile(checkpointer=checkpointer)


def _persist_citations(db: Session, run_id: int, items: list[dict]) -> None:
    existing_article_ids = set(
        db.scalars(select(AgentRunCitation.article_id).where(AgentRunCitation.run_id == run_id)).all()
    )
    for item in items:
        citation = ReviewedCitation.model_validate(item)
        if citation.article_id in existing_article_ids:
            continue
        db.add(
            AgentRunCitation(
                run_id=run_id,
                article_id=citation.article_id,
                law_version_id=citation.law_version_id,
                score=citation.score,
                keyword_score=citation.keyword_score or 0.0,
                semantic_score=citation.semantic_score or 0.0,
                review_status=citation.review_status,
                review_reason=citation.review_reason,
                verified=citation.verified,
            )
        )


def _persist_clarification_interrupt(
    db: Session,
    run: AgentRun,
    result: dict,
    payload: dict,
) -> None:
    round_number = int(payload["round"])
    clarification = db.scalar(
        select(AgentClarification).where(
            AgentClarification.run_id == run.id,
            AgentClarification.round_number == round_number,
        )
    )
    run.state_version += 1
    if clarification is None:
        clarification = AgentClarification(
            run_id=run.id,
            round_number=round_number,
            status="pending",
            questions=payload["questions"],
            requested_state_version=run.state_version,
        )
        db.add(clarification)
    run.status = "waiting_for_user"
    run.current_node = "clarify_user"
    run.progress = 35
    run.clarification_round = round_number
    run.facts = result.get("facts")
    run.node_traces = result.get("traces", [])
    run.model_name = result.get("model_name")
    run.completed_at = None
    db.commit()
    db.refresh(run)


def _persist_approval_interrupt(
    db: Session,
    run: AgentRun,
    result: dict,
    payload: dict,
) -> None:
    version_number = int(payload["report_version"])
    version = db.scalar(
        select(ReportVersion).where(
            ReportVersion.run_id == run.id,
            ReportVersion.version_number == version_number,
        )
    )
    if version is None:
        version = ReportVersion(
            run_id=run.id,
            version_number=version_number,
            title=result["report_title"],
            markdown=result["report_markdown"],
            facts_snapshot=result["facts"],
            citations_snapshot=result.get("reviewed_citations", []),
            change_summary=result.get("change_summary"),
            status="draft",
        )
        db.add(version)
        db.flush()
    approval = db.scalar(
        select(AgentApproval).where(
            AgentApproval.run_id == run.id,
            AgentApproval.report_version_id == version.id,
        )
    )
    run.state_version += 1
    if approval is None:
        approval = AgentApproval(
            run_id=run.id,
            report_version_id=version.id,
            round_number=version_number,
            status="pending",
            requested_state_version=run.state_version,
        )
        db.add(approval)
    _persist_citations(db, run.id, result.get("reviewed_citations", []))
    run.status = "waiting_for_approval"
    run.current_node = "approve_report"
    run.progress = 97
    run.current_report_version = version_number
    run.retry_count = result.get("retry_count", 0)
    run.facts = result.get("facts")
    run.report_title = result.get("report_title")
    run.report_markdown = result.get("report_markdown")
    run.evidence_gaps = result.get("evidence_gaps", [])
    run.node_traces = result.get("traces", [])
    run.model_name = result.get("model_name")
    run.completed_at = None
    db.commit()
    db.refresh(run)


def _persist_interrupt(db: Session, run: AgentRun, result: dict) -> bool:
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return False
    payload = interrupts[0].value
    if payload.get("type") == "clarification":
        _persist_clarification_interrupt(db, run, result, payload)
        return True
    if payload.get("type") == "approval":
        _persist_approval_interrupt(db, run, result, payload)
        return True
    raise RuntimeError("工作流返回了未知的人工待办类型")


def _latest_answered_clarification(db: Session, run_id: int) -> AgentClarification | None:
    return db.scalar(
        select(AgentClarification)
        .where(
            AgentClarification.run_id == run_id,
            AgentClarification.status == "answered",
        )
        .order_by(AgentClarification.round_number.desc())
    )


def _latest_decided_approval(db: Session, run_id: int) -> AgentApproval | None:
    return db.scalar(
        select(AgentApproval)
        .where(
            AgentApproval.run_id == run_id,
            AgentApproval.status != "pending",
        )
        .order_by(AgentApproval.round_number.desc())
    )


def execute_agent_run(db: Session, run: AgentRun) -> AgentRun:
    is_resume = run.status in {"resuming", "revising"}
    if not run.checkpoint_thread_id:
        run.checkpoint_thread_id = f"legal-run-{uuid4()}"
    if not run.trace_id:
        run.trace_id = uuid4().hex
    if not is_resume:
        run.status = "analyzing"
        run.current_node = "analyze_case"
        run.progress = 10
        run.started_at = datetime.now(UTC)
        run.clarification_round = 0
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    db.commit()

    root_observation = None
    try:
        with observe_span(
            "agent.invoke",
            run_id=run.id,
            trace_id=run.trace_id,
            attributes={
                "run.id": run.id,
                "thread.id": run.checkpoint_thread_id,
                "agent.mode": run.mode,
            },
        ) as root_observation:
            with _open_checkpointer(db) as checkpointer:
                graph = _build_graph(db, run.mode, checkpointer)
                config = {"configurable": {"thread_id": run.checkpoint_thread_id}}
                graph_input: WorkflowState | Command
                if is_resume:
                    if run.current_node == "approve_report":
                        approval = _latest_decided_approval(db, run.id)
                        if approval is None or approval.action is None:
                            raise RuntimeError("未找到可用于恢复工作流的审批决定")
                        graph_input = Command(
                            resume={
                                "action": approval.action,
                                "comment": approval.comment or "",
                            }
                        )
                    else:
                        clarification = _latest_answered_clarification(db, run.id)
                        if clarification is None:
                            raise RuntimeError("未找到可用于恢复工作流的追问回答")
                        graph_input = Command(resume={"answers": clarification.answers or []})
                else:
                    graph_input = {
                        "run_id": run.id,
                        "document_text": run.extracted_text,
                        "question": run.question,
                        "mode": run.mode,
                        "as_of_date": run.as_of_date.isoformat() if run.as_of_date else None,
                        "retry_count": 0,
                        "clarification_round": 0,
                        "report_version_number": 0,
                        "traces": [],
                        "observability_spans": [],
                    }
                result = graph.invoke(graph_input, config)
            root_record = root_observation.finish(
                status="interrupted" if result.get("__interrupt__") else "completed",
                provider="langgraph",
                model=result.get("model_name"),
                retry_count=int(result.get("retry_count", 0)),
            )
        result["observability_spans"] = [
            *result.get("observability_spans", []),
            root_record,
        ]
        persist_span_records(db, run, result["observability_spans"])
        if _persist_interrupt(db, run, result):
            return run

        approval_action = result.get("approval_action")
        version_number = result.get("report_version_number", run.current_report_version)
        version = db.scalar(
            select(ReportVersion).where(
                ReportVersion.run_id == run.id,
                ReportVersion.version_number == version_number,
            )
        )
        if approval_action == "reject":
            run.status = "rejected"
            run.current_node = "rejected"
            if version is not None:
                version.status = "rejected"
        else:
            run.status = "completed"
            run.current_node = "completed"
            run.approved_report_version = version_number
            if version is not None:
                version.status = "approved"
                version.approved_at = datetime.now(UTC)
        run.progress = 100
        run.state_version += 1
        run.retry_count = result.get("retry_count", 0)
        run.clarification_round = result.get("clarification_round", 0)
        run.facts = result["facts"]
        run.report_title = result["report_title"]
        run.report_markdown = result["report_markdown"]
        run.evidence_gaps = result.get("evidence_gaps", [])
        run.node_traces = result.get("traces", [])
        run.model_name = result.get("model_name")
        run.completed_at = datetime.now(UTC)
        _persist_citations(db, run.id, result.get("reviewed_citations", []))
    except Exception as error:
        run.status = "failed"
        run.current_node = "failed"
        run.error_code = type(error).__name__.upper()
        run.error_message = str(error)[:1000]
        run.completed_at = datetime.now(UTC)
        if root_observation is not None and root_observation._record is not None:
            persist_span_records(db, run, [root_observation._record])
    db.commit()
    db.refresh(run)
    return run
