from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Law(Base):
    __tablename__ = "laws"
    __table_args__ = (UniqueConstraint("name", name="uq_law_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), default="中华人民共和国")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LawVersion(Base):
    __tablename__ = "law_versions"
    __table_args__ = (UniqueConstraint("law_id", "version_label", name="uq_law_version_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_id: Mapped[int] = mapped_column(ForeignKey("laws.id", ondelete="CASCADE"), index=True)
    version_label: Mapped[str] = mapped_column(String(100))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="effective", index=True)
    source: Mapped[str] = mapped_column(String(500), default="项目内置教学版本")
    supersedes_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("law_versions.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegalArticle(Base):
    __tablename__ = "legal_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_name: Mapped[str] = mapped_column(String(200), index=True)
    article_number: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(500), default="项目内置样例")
    embedding: Mapped[list[float]] = mapped_column(JSON)
    law_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("law_versions.id"),
        nullable=True,
        index=True,
    )


class CaseRun(Base):
    __tablename__ = "case_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    case_type: Mapped[str] = mapped_column(String(100))
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_run_id: Mapped[int] = mapped_column(ForeignKey("case_runs.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("legal_articles.id"), index=True)
    law_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("law_versions.id"),
        nullable=True,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float)


class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"
    __table_args__ = (
        UniqueConstraint("article_id", "provider", "model", name="uq_article_embedding_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("legal_articles.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(200))
    dimensions: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    vector: Mapped[list[float]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(32), default="offline")
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    clarification_round: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    current_report_version: Mapped[int] = mapped_column(Integer, default=0)
    approved_report_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkpoint_thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    facts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_gaps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    node_traces: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Legacy compatibility only. New APIs and calculations use estimated_cost_cny.
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunSpan(Base):
    __tablename__ = "agent_run_spans"
    __table_args__ = (UniqueConstraint("run_id", "span_id", name="uq_agent_run_span"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        index=True,
    )
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16))
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    node: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Keep writing zero so databases created before the CNY migration remain insertable.
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentClarification(Base):
    __tablename__ = "agent_clarifications"
    __table_args__ = (
        UniqueConstraint("run_id", "round_number", name="uq_agent_clarification_round"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_clarification_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    questions: Mapped[list[dict]] = mapped_column(JSON)
    answers: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requested_state_version: Mapped[int] = mapped_column(Integer)
    answered_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("run_id", "version_number", name="uq_report_version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    markdown: Mapped[str] = mapped_column(Text)
    facts_snapshot: Mapped[dict] = mapped_column(JSON)
    citations_snapshot: Mapped[list[dict]] = mapped_column(JSON, default=list)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (
        UniqueConstraint("run_id", "report_version_id", name="uq_agent_approval_version"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_approval_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("report_versions.id", ondelete="CASCADE"),
        index=True,
    )
    round_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(100), default="本地审核人")
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    requested_state_version: Mapped[int] = mapped_column(Integer)
    decided_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunCitation(Base):
    __tablename__ = "agent_run_citations"
    __table_args__ = (UniqueConstraint("run_id", "article_id", name="uq_agent_run_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("legal_articles.id"), index=True)
    law_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("law_versions.id"),
        nullable=True,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float)
    keyword_score: Mapped[float] = mapped_column(Float, default=0.0)
    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
