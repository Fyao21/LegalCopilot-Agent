from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, AgentRunSpan
from app.schemas import (
    MonitoringNodeMetric,
    MonitoringOverview,
    MonitoringRunSummary,
    MonitoringSpan,
    RunMonitoringDetail,
)


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def percentile_95(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return float(ordered[index])


def persist_span_records(db: Session, run: AgentRun, records: list[dict[str, Any]]) -> None:
    if not run.trace_id:
        return
    existing = set(db.scalars(select(AgentRunSpan.span_id).where(AgentRunSpan.run_id == run.id)).all())
    for record in records:
        span_id = str(record.get("span_id") or "")
        if not span_id or span_id in existing:
            continue
        db.add(
            AgentRunSpan(
                run_id=run.id,
                trace_id=run.trace_id,
                span_id=span_id,
                parent_span_id=record.get("parent_span_id"),
                name=str(record.get("name") or "unknown"),
                node=record.get("node"),
                status=str(record.get("status") or "completed"),
                duration_ms=max(0, int(record.get("duration_ms") or 0)),
                provider=record.get("provider"),
                model=record.get("model"),
                input_tokens=max(0, int(record.get("input_tokens") or 0)),
                output_tokens=max(0, int(record.get("output_tokens") or 0)),
                estimated_cost_usd=max(0.0, float(record.get("estimated_cost_usd") or 0.0)),
                retry_count=max(0, int(record.get("retry_count") or 0)),
                fallback_reason=record.get("fallback_reason"),
                error_code=record.get("error_code"),
                attributes=record.get("attributes") or {},
                started_at=_parse_datetime(record["started_at"]),
                completed_at=_parse_datetime(record["completed_at"]),
            )
        )
        existing.add(span_id)
    db.flush()
    spans = db.scalars(select(AgentRunSpan).where(AgentRunSpan.run_id == run.id)).all()
    root_spans = [span for span in spans if span.name == "agent.invoke"]
    metered_spans = [span for span in spans if span.name in {"gen_ai.chat", "gen_ai.embeddings"}]
    run.total_duration_ms = sum(span.duration_ms for span in root_spans)
    run.input_tokens = sum(span.input_tokens for span in metered_spans)
    run.output_tokens = sum(span.output_tokens for span in metered_spans)
    run.estimated_cost_usd = round(
        sum(span.estimated_cost_usd for span in metered_spans),
        8,
    )
    run.fallback_count = sum(1 for span in metered_spans if span.fallback_reason)


def _span_schema(span: AgentRunSpan) -> MonitoringSpan:
    return MonitoringSpan(
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        node=span.node,
        status=span.status,
        duration_ms=span.duration_ms,
        provider=span.provider,
        model=span.model,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        estimated_cost_usd=span.estimated_cost_usd,
        retry_count=span.retry_count,
        fallback_reason=span.fallback_reason,
        error_code=span.error_code,
        attributes=span.attributes or {},
        started_at=span.started_at,
        completed_at=span.completed_at,
    )


def build_run_monitoring(db: Session, run: AgentRun) -> RunMonitoringDetail | None:
    if not run.trace_id:
        return None
    spans = db.scalars(
        select(AgentRunSpan)
        .where(AgentRunSpan.run_id == run.id)
        .order_by(AgentRunSpan.started_at, AgentRunSpan.id)
    ).all()
    node_spans = [span for span in spans if span.node and span.name.startswith("agent.")]
    slowest = max(node_spans, key=lambda span: span.duration_ms, default=None)
    return RunMonitoringDetail(
        run_id=run.id,
        trace_id=run.trace_id,
        status=run.status,
        mode=run.mode,
        model=run.model_name,
        total_duration_ms=run.total_duration_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        fallback_count=run.fallback_count,
        retry_count=run.retry_count,
        slowest_node=slowest.node if slowest else None,
        slowest_node_duration_ms=slowest.duration_ms if slowest else 0,
        started_at=run.started_at,
        completed_at=run.completed_at,
        spans=[_span_schema(span) for span in spans],
    )


def build_monitoring_overview(db: Session, days: int) -> MonitoringOverview:
    since = datetime.now(UTC) - timedelta(days=days)
    runs = db.scalars(
        select(AgentRun)
        .where(
            AgentRun.created_at >= since,
            AgentRun.trace_id.is_not(None),
        )
        .order_by(AgentRun.created_at.desc())
    ).all()
    run_ids = [run.id for run in runs]
    spans = (
        db.scalars(
            select(AgentRunSpan).where(AgentRunSpan.run_id.in_(run_ids)).order_by(AgentRunSpan.started_at)
        ).all()
        if run_ids
        else []
    )
    durations = [run.total_duration_ms for run in runs if run.total_duration_ms > 0]
    fallback_runs = sum(1 for run in runs if run.fallback_count > 0)
    operational_success = sum(1 for run in runs if run.status != "failed")
    node_durations: dict[str, list[int]] = {}
    for span in spans:
        if not span.node or not span.name.startswith("agent."):
            continue
        node_durations.setdefault(span.node, []).append(span.duration_ms)
    node_metrics = [
        MonitoringNodeMetric(
            node=node,
            sample_count=len(values),
            average_duration_ms=round(sum(values) / len(values), 2),
            p95_duration_ms=percentile_95(values),
        )
        for node, values in sorted(node_durations.items())
    ]
    return MonitoringOverview(
        days=days,
        run_count=len(runs),
        success_rate=round(operational_success / len(runs), 4) if runs else 0.0,
        fallback_rate=round(fallback_runs / len(runs), 4) if runs else 0.0,
        average_duration_ms=round(sum(durations) / len(durations), 2) if durations else 0.0,
        p95_duration_ms=percentile_95(durations),
        total_input_tokens=sum(run.input_tokens for run in runs),
        total_output_tokens=sum(run.output_tokens for run in runs),
        total_estimated_cost_usd=round(
            sum(run.estimated_cost_usd for run in runs),
            8,
        ),
        node_metrics=node_metrics,
        recent_runs=[
            MonitoringRunSummary(
                run_id=run.id,
                trace_id=run.trace_id or "",
                status=run.status,
                mode=run.mode,
                model=run.model_name,
                total_duration_ms=run.total_duration_ms,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                estimated_cost_usd=run.estimated_cost_usd,
                fallback_count=run.fallback_count,
                retry_count=run.retry_count,
                created_at=run.created_at,
            )
            for run in runs[:20]
        ],
    )
