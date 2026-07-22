from datetime import datetime

from pydantic import BaseModel, Field


class CaseFacts(BaseModel):
    case_type: str = "未识别"
    parties: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    dispute_focuses: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)
    questions_for_user: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    article_id: int
    law_name: str
    article_number: str
    excerpt: str
    source: str
    score: float
    keyword_score: float | None = None
    semantic_score: float | None = None


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
    facts: CaseFacts
    citations: list[Citation]
    notice: str = "本结果仅用于技术演示，不构成法律意见。"


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=5, ge=1, le=20)


class HealthResponse(BaseModel):
    status: str
    article_count: int


class AgentRunCreated(BaseModel):
    run_id: int
    status: str
    status_url: str
    report_url: str


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
    mode: str
    facts: CaseFacts | None = None
    traces: list[NodeTrace] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ReportSection(BaseModel):
    heading: str
    content: str
    citation_ids: list[int] = Field(default_factory=list)


class ReportDraft(BaseModel):
    title: str
    analysis: str
    suggestions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    run_id: int
    title: str
    markdown: str
    facts: CaseFacts
    evidence_gaps: list[str] = Field(default_factory=list)
    citations: list[ReviewedCitation] = Field(default_factory=list)
    notice: str = "本结果仅用于技术演示，不构成法律意见。"
    model: str | None = None


class LegalArticleDetail(BaseModel):
    article_id: int
    law_name: str
    article_number: str
    content: str
    source: str
