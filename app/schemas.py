from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ApprovalAction = Literal["approve", "request_changes", "reject"]
ReportVersionStatus = Literal["draft", "approved", "superseded", "rejected"]
LawEffectStatus = Literal["effective", "amended", "repealed", "legacy"]


def _approval_actions() -> list[ApprovalAction]:
    return ["approve", "request_changes", "reject"]


def _normalize_string_list(value: Any) -> Any:
    """Accept common LLM list mistakes without weakening the public response type."""
    if value is None:
        return []
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not normalized:
        return []
    lines = [
        item.strip(" \t\r\n-•·0123456789.、）)")
        for item in normalized.replace("；", "\n").replace(";", "\n").splitlines()
    ]
    return [item for item in lines if item]


class CaseFacts(BaseModel):
    case_type: str = "未识别"
    parties: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    dispute_focuses: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)
    questions_for_user: list[str] = Field(default_factory=list)

    @field_validator("case_type")
    @classmethod
    def validate_case_type(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("案件类型不能为空")
        return normalized

    @field_validator(
        "parties",
        "key_facts",
        "claims",
        "dispute_focuses",
        "missing_information",
        "questions_for_user",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: Any) -> Any:
        return _normalize_string_list(value)


class Citation(BaseModel):
    article_id: int
    law_name: str
    article_number: str
    excerpt: str
    source: str
    score: float
    keyword_score: float | None = None
    semantic_score: float | None = None
    law_id: int | None = None
    law_version_id: int | None = None
    version_label: str = "未标注版本"
    effect_status: LawEffectStatus = "legacy"
    effective_from: date | None = None
    effective_to: date | None = None


class ReviewedCitation(Citation):
    review_status: str = "pending"
    review_reason: str | None = None
    verified: bool = False


class CitationReviewItem(BaseModel):
    article_id: int
    supported: bool
    reason: str


class CitationReviewBatch(BaseModel):
    reviews: list[CitationReviewItem] = Field(default_factory=list)


class CaseAnalysisResponse(BaseModel):
    run_id: int
    as_of_date: date | None = None
    facts: CaseFacts
    citations: list[Citation]
    notice: str = "本结果仅用于技术演示，不构成法律意见。"


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=5, ge=1, le=20)
    as_of_date: date | None = None


class HealthResponse(BaseModel):
    status: str
    article_count: int


class QuestionExample(BaseModel):
    example_id: str
    category: str
    detail_level: Literal["brief", "detailed"]
    question: str


class QuestionExamplesResponse(BaseModel):
    count: int
    requested_category: str | None = None
    requested_detail_level: Literal["brief", "detailed"]
    available_categories: list[str]
    examples: list[QuestionExample]


class AgentRunCreated(BaseModel):
    run_id: int
    status: str
    as_of_date: date | None = None
    trace_id: str
    status_url: str
    report_url: str
    monitoring_url: str


class ClarificationQuestion(BaseModel):
    question_id: str
    prompt: str
    missing_field: str | None = None
    required: bool = True


class ClarificationPendingAction(BaseModel):
    action_id: int
    type: Literal["clarification"] = "clarification"
    round: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    questions: list[ClarificationQuestion]


class ApprovalPendingAction(BaseModel):
    action_id: int
    type: Literal["approval"] = "approval"
    report_version: int = Field(ge=1)
    report_version_id: int
    title: str
    change_summary: str | None = None
    allowed_actions: list[ApprovalAction] = Field(default_factory=_approval_actions)


class PendingActionResponse(BaseModel):
    run_id: int
    status: str
    state_version: int = Field(ge=0)
    action: ClarificationPendingAction | ApprovalPendingAction | None = None


class ClarificationAnswer(BaseModel):
    question_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=5000)

    @field_validator("question_id", "answer")
    @classmethod
    def strip_answer_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("问题编号和回答不能为空")
        return normalized


class ClarificationSubmission(BaseModel):
    expected_state_version: int = Field(ge=0)
    answers: list[ClarificationAnswer] = Field(min_length=1, max_length=5)

    @field_validator("answers")
    @classmethod
    def reject_duplicate_question_ids(cls, answers: list[ClarificationAnswer]) -> list[ClarificationAnswer]:
        question_ids = [answer.question_id for answer in answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("同一个问题不能重复回答")
        return answers


class ClarificationSubmissionResponse(BaseModel):
    run_id: int
    status: str
    state_version: int = Field(ge=0)
    replayed: bool = False
    status_url: str
    message: str


class ApprovalSubmission(BaseModel):
    expected_state_version: int = Field(ge=0)
    action: ApprovalAction
    comment: str = Field(default="", max_length=5000)
    reviewer: str = Field(default="本地审核人", min_length=1, max_length=100)

    @field_validator("comment", "reviewer")
    @classmethod
    def strip_approval_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("reviewer")
    @classmethod
    def reject_blank_reviewer(cls, value: str) -> str:
        if not value:
            raise ValueError("审核人不能为空")
        return value


class ApprovalSubmissionResponse(BaseModel):
    run_id: int
    action: ApprovalAction
    status: str
    state_version: int = Field(ge=0)
    report_version: int = Field(ge=1)
    replayed: bool = False
    status_url: str
    message: str


class NodeTrace(BaseModel):
    node: str
    status: str
    duration_ms: int
    action_summary: str
    error_code: str | None = None


class AgentRunStatus(BaseModel):
    run_id: int
    status: str
    current_node: str | None = None
    progress: int = Field(ge=0, le=100)
    retry_count: int = 0
    clarification_round: int = 0
    state_version: int = 0
    current_report_version: int = 0
    approved_report_version: int | None = None
    pending_action_url: str | None = None
    mode: str
    as_of_date: date | None = None
    execution_engine: str
    model: str | None = None
    trace_id: str
    monitoring_url: str
    total_duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback_count: int = 0
    facts: CaseFacts | None = None
    traces: list[NodeTrace] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MonitoringSpan(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    name: str
    node: str | None = None
    status: str
    duration_ms: int = 0
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    retry_count: int = 0
    fallback_reason: str | None = None
    error_code: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime


class RunMonitoringDetail(BaseModel):
    run_id: int
    trace_id: str
    status: str
    mode: str
    model: str | None = None
    total_duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback_count: int = 0
    retry_count: int = 0
    slowest_node: str | None = None
    slowest_node_duration_ms: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    spans: list[MonitoringSpan] = Field(default_factory=list)


class MonitoringNodeMetric(BaseModel):
    node: str
    sample_count: int
    average_duration_ms: float
    p95_duration_ms: float


class MonitoringRunSummary(BaseModel):
    run_id: int
    trace_id: str
    status: str
    mode: str
    model: str | None = None
    total_duration_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    fallback_count: int
    retry_count: int
    created_at: datetime | None = None


class MonitoringOverview(BaseModel):
    days: int
    run_count: int
    success_rate: float
    fallback_rate: float
    average_duration_ms: float
    p95_duration_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_usd: float
    node_metrics: list[MonitoringNodeMetric] = Field(default_factory=list)
    recent_runs: list[MonitoringRunSummary] = Field(default_factory=list)


class ReportSection(BaseModel):
    heading: str
    content: str
    citation_ids: list[int] = Field(default_factory=list)


class ReportDraft(BaseModel):
    title: str
    analysis: str
    suggestions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)

    @field_validator("suggestions", "evidence_gaps", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: Any) -> Any:
        return _normalize_string_list(value)


class ReportRevision(BaseModel):
    markdown: str = Field(min_length=20)
    change_summary: str = Field(min_length=2, max_length=500)


class ReportResponse(BaseModel):
    run_id: int
    as_of_date: date | None = None
    version_number: int = Field(ge=1)
    approval_status: ReportVersionStatus
    is_final: bool
    title: str
    markdown: str
    facts: CaseFacts
    evidence_gaps: list[str] = Field(default_factory=list)
    citations: list[ReviewedCitation] = Field(default_factory=list)
    notice: str = "本结果仅用于技术演示，不构成法律意见。"
    model: str | None = None


class ReportVersionSummary(BaseModel):
    version_number: int = Field(ge=1)
    status: ReportVersionStatus
    title: str
    change_summary: str | None = None
    created_at: datetime | None = None
    approved_at: datetime | None = None


class ReportVersionDetail(ReportVersionSummary):
    markdown: str
    facts: CaseFacts
    citations: list[ReviewedCitation] = Field(default_factory=list)
    diff_from_previous: str = ""


class LegalArticleDetail(BaseModel):
    article_id: int
    law_name: str
    article_number: str
    content: str
    source: str
    law_id: int | None = None
    law_version_id: int | None = None
    version_label: str = "未标注版本"
    effect_status: LawEffectStatus = "legacy"
    effective_from: date | None = None
    effective_to: date | None = None


class LegalArticleCreate(BaseModel):
    law_name: str = Field(min_length=2, max_length=200)
    article_number: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=2, max_length=20000)
    source: str = Field(min_length=2, max_length=500)

    @field_validator("law_name", "article_number", "content", "source")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空白")
        return normalized


class KnowledgeBatchItem(BaseModel):
    filename: str
    status: Literal["created", "duplicate", "invalid"]
    article_id: int | None = None
    law_name: str | None = None
    article_number: str | None = None
    message: str


class KnowledgeBatchResponse(BaseModel):
    total: int
    created_count: int
    duplicate_count: int
    invalid_count: int
    items: list[KnowledgeBatchItem]


class KnowledgeNormalizationResponse(BaseModel):
    original_filename: str
    standardized_filename: str
    law_name: str | None = None
    article_number: str | None = None
    source: str | None = None
    content: str
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    multiple_articles_detected: bool = False
    ready_for_import: bool
    requires_human_review: bool = True
    standardized_text: str
    model: str
