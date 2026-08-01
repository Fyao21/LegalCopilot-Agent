from __future__ import annotations

import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import (
    NonRecordingSpan,
    Span,
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
    TraceState,
)

from app.config import get_settings

ALLOWED_SPAN_ATTRIBUTES = frozenset(
    {
        "run.id",
        "thread.id",
        "agent.mode",
        "agent.node",
        "agent.status",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "retrieval.provider",
        "retrieval.candidate_count",
        "retrieval.verified_count",
        "fallback.reason",
        "retry.count",
    }
)

SENSITIVE_ATTRIBUTE_FRAGMENTS = (
    "api_key",
    "authorization",
    "document",
    "material",
    "password",
    "prompt",
    "question",
    "secret",
    "token_value",
)

_provider_configured = False


def configure_telemetry() -> None:
    global _provider_configured
    if _provider_configured or not get_settings().observability_enabled:
        return
    current = trace.get_tracer_provider()
    if current.__class__.__name__ == "ProxyTracerProvider":
        trace.set_tracer_provider(
            TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": get_settings().telemetry_service_name,
                        "service.version": "1.2.0",
                    }
                )
            )
        )
    _provider_configured = True


def get_tracer():
    configure_telemetry()
    return trace.get_tracer("legal_copilot.agent", "1.2.0")


def sanitize_span_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        normalized = key.lower()
        if key not in ALLOWED_SPAN_ATTRIBUTES:
            continue
        if any(fragment in normalized for fragment in SENSITIVE_ATTRIBUTE_FRAGMENTS):
            continue
        if isinstance(value, (str, bool, int, float)):
            safe[key] = value
    return safe


def estimate_cost_usd(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    operation: str = "chat",
) -> float:
    settings = get_settings()
    if operation == "embedding":
        cost = input_tokens * settings.embedding_cost_per_million_usd / 1_000_000
    else:
        cost = (
            input_tokens * settings.llm_input_cost_per_million_usd
            + output_tokens * settings.llm_output_cost_per_million_usd
        ) / 1_000_000
    return round(cost, 8)


def _trace_parent_context(trace_id: str | None):
    if not trace_id:
        return None
    try:
        numeric_trace_id = int(trace_id, 16)
    except ValueError:
        return None
    if numeric_trace_id <= 0:
        return None
    parent = NonRecordingSpan(
        SpanContext(
            trace_id=numeric_trace_id,
            span_id=secrets.randbits(64) or 1,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
            trace_state=TraceState(),
        )
    )
    return trace.set_span_in_context(parent, otel_context.get_current())


@dataclass
class SpanObservation:
    span: Span
    name: str
    node: str | None
    started_at: datetime
    started_perf: float
    base_attributes: dict[str, Any]
    _record: dict[str, Any] | None = None

    def finish(
        self,
        *,
        status: str = "completed",
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        retry_count: int = 0,
        fallback_reason: str | None = None,
        error_code: str | None = None,
        attributes: dict[str, Any] | None = None,
        operation: str = "chat",
    ) -> dict[str, Any]:
        if self._record is not None:
            return self._record
        completed_at = datetime.now(UTC)
        duration_ms = max(0, round((time.perf_counter() - self.started_perf) * 1000))
        merged = {
            **self.base_attributes,
            **(attributes or {}),
            "agent.status": status,
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": model,
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "fallback.reason": fallback_reason,
            "retry.count": retry_count,
        }
        safe_attributes = sanitize_span_attributes(merged)
        for key, value in safe_attributes.items():
            self.span.set_attribute(key, value)
        if error_code or status == "failed":
            self.span.set_status(Status(StatusCode.ERROR, error_code or "span failed"))
        else:
            self.span.set_status(Status(StatusCode.OK))
        span_context = self.span.get_span_context()
        parent = getattr(self.span, "parent", None)
        parent_span_id = None
        parent_span_id_value = getattr(parent, "span_id", None)
        if isinstance(parent_span_id_value, int) and parent_span_id_value:
            parent_span_id = f"{parent_span_id_value:016x}"
        self._record = {
            "trace_id": f"{span_context.trace_id:032x}",
            "span_id": f"{span_context.span_id:016x}",
            "parent_span_id": parent_span_id,
            "name": self.name,
            "node": self.node,
            "status": status,
            "duration_ms": duration_ms,
            "provider": provider,
            "model": model,
            "input_tokens": max(0, input_tokens),
            "output_tokens": max(0, output_tokens),
            "estimated_cost_usd": estimate_cost_usd(
                input_tokens=max(0, input_tokens),
                output_tokens=max(0, output_tokens),
                operation=operation,
            ),
            "retry_count": max(0, retry_count),
            "fallback_reason": fallback_reason[:500] if fallback_reason else None,
            "error_code": error_code,
            "attributes": safe_attributes,
            "started_at": self.started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }
        return self._record


@contextmanager
def observe_span(
    name: str,
    *,
    run_id: int | None = None,
    node: str | None = None,
    trace_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[SpanObservation]:
    safe_attributes = sanitize_span_attributes(
        {
            **(attributes or {}),
            "run.id": run_id,
            "agent.node": node,
        }
    )
    parent_context = _trace_parent_context(trace_id)
    with get_tracer().start_as_current_span(
        name,
        context=parent_context,
        attributes=safe_attributes,
    ) as span:
        observation = SpanObservation(
            span=span,
            name=name,
            node=node,
            started_at=datetime.now(UTC),
            started_perf=time.perf_counter(),
            base_attributes=safe_attributes,
        )
        try:
            yield observation
        except Exception as error:
            observation.finish(
                status="failed",
                error_code=type(error).__name__.upper(),
            )
            raise
        finally:
            if observation._record is None:
                observation.finish()
