import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from difflib import unified_diff
from typing import Literal, cast
from uuid import uuid4

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.llm import LLMClientError, get_llm_client
from app.migrations import ensure_runtime_schema
from app.models import (
    AgentApproval,
    AgentClarification,
    AgentRun,
    AgentRunCitation,
    CaseRun,
    LawVersion,
    LegalArticle,
    ReportVersion,
    RetrievalLog,
)
from app.schemas import (
    AgentRunCreated,
    AgentRunStatus,
    ApprovalAction,
    ApprovalPendingAction,
    ApprovalSubmission,
    ApprovalSubmissionResponse,
    CaseAnalysisResponse,
    CaseFacts,
    Citation,
    ClarificationPendingAction,
    ClarificationQuestion,
    ClarificationSubmission,
    ClarificationSubmissionResponse,
    HealthResponse,
    KnowledgeBatchItem,
    KnowledgeBatchResponse,
    KnowledgeNormalizationResponse,
    LawEffectStatus,
    LegalArticleCreate,
    LegalArticleDetail,
    MonitoringOverview,
    PendingActionResponse,
    QuestionExample,
    QuestionExamplesResponse,
    ReportResponse,
    ReportVersionDetail,
    ReportVersionStatus,
    ReportVersionSummary,
    ReviewedCitation,
    RunMonitoringDetail,
    SearchRequest,
)
from app.services.case_analyzer import analyze_case
from app.services.embedding_index import ensure_article_embeddings
from app.services.embedding_provider import get_embedding_provider
from app.services.embeddings import embed
from app.services.knowledge_import import (
    MAX_BATCH_FILE_BYTES,
    MAX_BATCH_FILES,
    MAX_BATCH_TOTAL_BYTES,
    KnowledgeImportError,
    parse_knowledge_text_file,
)
from app.services.knowledge_normalizer import (
    decode_unstructured_knowledge_file,
    normalize_knowledge_text,
)
from app.services.law_versioning import attach_article_to_current_version, ensure_law_version_data
from app.services.monitoring import build_monitoring_overview, build_run_monitoring
from app.services.observability import configure_telemetry
from app.services.question_examples import AVAILABLE_CATEGORIES, generate_question_examples
from app.services.report_export import markdown_to_pdf
from app.services.retrieval_service import retrieve_articles_configured
from app.services.seed import seed_sample_laws
from app.services.upload_security import UploadValidationError, read_and_extract_upload
from app.tasks import execute_agent_run_by_id

logger = logging.getLogger("legal_copilot.api")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_runtime_schema(engine)
    with SessionLocal() as db:
        seed_sample_laws(db)
        ensure_law_version_data(db)
        ensure_article_embeddings(db, get_embedding_provider(force_offline=True))
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="可追溯法律检索与案件要素分析 MVP",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key"],
    expose_headers=[
        "Content-Disposition",
        "X-Request-ID",
        "X-Embedding-Provider",
        "X-Embedding-Model",
        "X-Law-As-Of-Date",
        "X-Trace-ID",
    ],
)
configure_telemetry()
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    span_context = trace.get_current_span().get_span_context()
    request_trace_id = f"{span_context.trace_id:032x}" if span_context.is_valid else uuid4().hex
    request.state.trace_id = request_trace_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            json.dumps(
                {
                    "event": "request_failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "trace_id": request_trace_id,
                },
                ensure_ascii=False,
            )
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Trace-ID"] = request_trace_id
    logger.info(
        json.dumps(
            {
                "event": "request_completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "trace_id": request_trace_id,
            },
            ensure_ascii=False,
        )
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    count = db.scalar(select(func.count()).select_from(LegalArticle)) or 0
    return HealthResponse(status="ok", article_count=count)


@app.get(
    "/api/v1/examples/questions/random",
    response_model=QuestionExamplesResponse,
    tags=["案件示例"],
)
def random_question_examples(
    count: int = Query(default=3, ge=1, le=10),
    category: str | None = Query(default=None, max_length=50),
    detail_level: Literal["brief", "detailed"] = Query(default="brief"),
) -> QuestionExamplesResponse:
    try:
        examples = generate_question_examples(count, category, detail_level)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return QuestionExamplesResponse(
        count=len(examples),
        requested_category=category.strip() if category else None,
        requested_detail_level=detail_level,
        available_categories=list(AVAILABLE_CATEGORIES),
        examples=[QuestionExample.model_validate(example) for example in examples],
    )


@app.post("/api/v1/articles/search", response_model=list[Citation])
def search_articles(
    request: SearchRequest, response: Response, db: Session = Depends(get_db)
) -> list[Citation]:
    result = retrieve_articles_configured(
        db,
        request.query,
        request.limit,
        as_of_date=request.as_of_date,
    )
    response.headers["X-Embedding-Provider"] = result.provider
    response.headers["X-Embedding-Model"] = result.model
    response.headers["X-Law-As-Of-Date"] = result.as_of_date.isoformat()
    return result.citations


@app.post(
    "/api/v1/knowledge/articles",
    response_model=LegalArticleDetail,
    status_code=201,
    tags=["知识库"],
)
def create_knowledge_article(
    request: LegalArticleCreate, db: Session = Depends(get_db)
) -> LegalArticleDetail:
    existing = db.scalar(
        select(LegalArticle).where(
            LegalArticle.law_name == request.law_name,
            LegalArticle.article_number == request.article_number,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="相同法律名称和条文编号已经存在")

    article = LegalArticle(
        law_name=request.law_name,
        article_number=request.article_number,
        content=request.content,
        source=request.source,
        embedding=embed(request.content),
    )
    db.add(article)
    db.flush()
    version = attach_article_to_current_version(db, article)
    ensure_article_embeddings(db, get_embedding_provider(force_offline=True))
    db.refresh(article)
    return LegalArticleDetail(
        article_id=article.id,
        law_name=article.law_name,
        article_number=article.article_number,
        content=article.content,
        source=article.source,
        law_id=version.law_id,
        law_version_id=version.id,
        version_label=version.version_label,
        effect_status=cast(LawEffectStatus, version.status),
        effective_from=version.effective_from,
        effective_to=version.effective_to,
    )


@app.post(
    "/api/v1/knowledge/articles/batch",
    response_model=KnowledgeBatchResponse,
    tags=["知识库"],
)
async def create_knowledge_articles_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> KnowledgeBatchResponse:
    if not files:
        raise HTTPException(status_code=422, detail="请至少上传一个 TXT 文件")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"每批最多上传 {MAX_BATCH_FILES} 个文件")

    items: list[KnowledgeBatchItem | None] = [None] * len(files)
    parsed: list[tuple[int, str, LegalArticleCreate]] = []
    total_bytes = 0
    for index, upload in enumerate(files):
        filename = upload.filename or f"未命名-{index + 1}.txt"
        data = await upload.read(MAX_BATCH_FILE_BYTES + 1)
        await upload.close()
        total_bytes += len(data)
        if total_bytes > MAX_BATCH_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="整批文件总大小不能超过 8 MB")
        try:
            result = parse_knowledge_text_file(filename, data)
            parsed.append((index, result.filename, result.article))
        except KnowledgeImportError as error:
            items[index] = KnowledgeBatchItem(
                filename=filename,
                status="invalid",
                message=str(error),
            )

    keys = [(article.law_name, article.article_number) for _, _, article in parsed]
    existing_keys: set[tuple[str, str]] = set()
    if keys:
        existing_keys = {
            (row[0], row[1])
            for row in db.execute(
                select(LegalArticle.law_name, LegalArticle.article_number).where(
                    tuple_(LegalArticle.law_name, LegalArticle.article_number).in_(keys)
                )
            ).all()
        }

    batch_keys: set[tuple[str, str]] = set()
    created_rows: list[tuple[int, str, LegalArticle]] = []
    for index, filename, request in parsed:
        key = (request.law_name, request.article_number)
        if key in existing_keys or key in batch_keys:
            items[index] = KnowledgeBatchItem(
                filename=filename,
                status="duplicate",
                law_name=request.law_name,
                article_number=request.article_number,
                message="相同法律名称和条文编号已经存在",
            )
            continue
        batch_keys.add(key)
        article = LegalArticle(
            law_name=request.law_name,
            article_number=request.article_number,
            content=request.content,
            source=request.source,
            embedding=embed(request.content),
        )
        db.add(article)
        created_rows.append((index, filename, article))

    if created_rows:
        db.flush()
        for _, _, article in created_rows:
            attach_article_to_current_version(db, article)
        ensure_article_embeddings(db, get_embedding_provider(force_offline=True))
        for index, filename, article in created_rows:
            items[index] = KnowledgeBatchItem(
                filename=filename,
                status="created",
                article_id=article.id,
                law_name=article.law_name,
                article_number=article.article_number,
                message="法规已保存并建立检索索引",
            )

    completed_items = [item for item in items if item is not None]
    created_count = sum(item.status == "created" for item in completed_items)
    duplicate_count = sum(item.status == "duplicate" for item in completed_items)
    invalid_count = sum(item.status == "invalid" for item in completed_items)
    return KnowledgeBatchResponse(
        total=len(files),
        created_count=created_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        items=completed_items,
    )


@app.post(
    "/api/v1/knowledge/articles/normalize",
    response_model=KnowledgeNormalizationResponse,
    tags=["知识库"],
)
async def normalize_knowledge_article(file: UploadFile = File(...)) -> KnowledgeNormalizationResponse:
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in {"text/plain", "application/octet-stream"}:
        await file.close()
        raise HTTPException(status_code=415, detail="智能整理仅支持 TXT 文本文件")
    try:
        data = await file.read(MAX_BATCH_FILE_BYTES + 1)
    finally:
        await file.close()
    try:
        filename, text = decode_unstructured_knowledge_file(file.filename or "未命名.txt", data)
    except KnowledgeImportError as error:
        status_code = 413 if len(data) > MAX_BATCH_FILE_BYTES else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    llm = get_llm_client()
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="智能整理需要启用在线模型：请设置 OFFLINE_MODE=false 并配置 LLM API Key",
        )
    try:
        result = normalize_knowledge_text(filename, text, llm)
    except LLMClientError as error:
        raise HTTPException(
            status_code=502,
            detail=f"模型未能完成 TXT 整理（{error.code}）：{error}",
        ) from error
    return KnowledgeNormalizationResponse.model_validate(result)


@app.get("/api/v1/articles/{article_id}", response_model=LegalArticleDetail)
def get_article(article_id: int, db: Session = Depends(get_db)) -> LegalArticleDetail:
    article = db.get(LegalArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="未找到指定法规条文")
    version = db.get(LawVersion, article.law_version_id) if article.law_version_id else None
    return LegalArticleDetail(
        article_id=article.id,
        law_name=article.law_name,
        article_number=article.article_number,
        content=article.content,
        source=article.source,
        law_id=version.law_id if version else None,
        law_version_id=version.id if version else None,
        version_label=version.version_label if version else "未标注版本",
        effect_status=cast(LawEffectStatus, version.status) if version else "legacy",
        effective_from=version.effective_from if version else None,
        effective_to=version.effective_to if version else None,
    )


@app.post("/api/v1/cases", response_model=CaseAnalysisResponse, status_code=201)
async def create_case(
    question: str = Form(..., min_length=2, max_length=5000),
    as_of_date: date | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> CaseAnalysisResponse:
    try:
        filename, extracted_text = await read_and_extract_upload(
            file,
            max_bytes=settings.max_upload_bytes,
            timeout_seconds=settings.document_parse_timeout_seconds,
        )
    except UploadValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    if not extracted_text and not question.strip():
        raise HTTPException(status_code=422, detail="至少提供案件问题或文件内容")

    facts = analyze_case(extracted_text, question)
    run = CaseRun(
        filename=filename,
        question=question,
        extracted_text=extracted_text,
        case_type=facts.case_type,
        as_of_date=as_of_date,
    )
    db.add(run)
    db.flush()
    query = "\n".join([question, *facts.dispute_focuses, *facts.claims])
    citations = retrieve_articles_configured(
        db,
        query,
        settings.top_k,
        as_of_date=as_of_date,
    ).citations
    db.add_all(
        RetrievalLog(
            case_run_id=run.id,
            article_id=citation.article_id,
            law_version_id=citation.law_version_id,
            score=citation.score,
        )
        for citation in citations
    )
    db.commit()
    return CaseAnalysisResponse(
        run_id=run.id,
        as_of_date=as_of_date,
        facts=facts,
        citations=citations,
    )


def _get_agent_run_or_404(db: Session, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="未找到指定 Agent 任务")
    return run


def _get_run_citations(db: Session, run_id: int) -> list[ReviewedCitation]:
    rows = db.execute(
        select(AgentRunCitation, LegalArticle, LawVersion)
        .join(LegalArticle, LegalArticle.id == AgentRunCitation.article_id)
        .outerjoin(LawVersion, LawVersion.id == AgentRunCitation.law_version_id)
        .where(AgentRunCitation.run_id == run_id)
        .order_by(AgentRunCitation.score.desc())
    ).all()
    return [
        ReviewedCitation(
            article_id=article.id,
            law_name=article.law_name,
            article_number=article.article_number,
            excerpt=article.content,
            source=article.source,
            score=log.score,
            keyword_score=log.keyword_score,
            semantic_score=log.semantic_score,
            review_status=log.review_status,
            review_reason=log.review_reason,
            verified=log.verified,
            law_id=version.law_id if version else None,
            law_version_id=version.id if version else None,
            version_label=version.version_label if version else "未标注版本",
            effect_status=cast(LawEffectStatus, version.status) if version else "legacy",
            effective_from=version.effective_from if version else None,
            effective_to=version.effective_to if version else None,
        )
        for log, article, version in rows
    ]


def _get_report_version(
    db: Session,
    run_id: int,
    version_number: int | None = None,
) -> ReportVersion | None:
    statement = select(ReportVersion).where(ReportVersion.run_id == run_id)
    if version_number is None:
        statement = statement.order_by(ReportVersion.version_number.desc())
    else:
        statement = statement.where(ReportVersion.version_number == version_number)
    return db.scalar(statement)


def _version_citations(version: ReportVersion) -> list[ReviewedCitation]:
    return [ReviewedCitation.model_validate(item) for item in (version.citations_snapshot or [])]


def _version_diff(previous: ReportVersion | None, current: ReportVersion) -> str:
    if previous is None:
        return ""
    return "\n".join(
        unified_diff(
            previous.markdown.splitlines(),
            current.markdown.splitlines(),
            fromfile=f"v{previous.version_number}",
            tofile=f"v{current.version_number}",
            lineterm="",
        )
    )


@app.post("/api/v1/runs", response_model=AgentRunCreated, status_code=202)
async def create_agent_run(
    request: Request,
    background_tasks: BackgroundTasks,
    question: str = Form(..., min_length=2, max_length=5000),
    mode: str = Form(default="offline"),
    as_of_date: date | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> AgentRunCreated:
    if mode not in {"offline", "agent"}:
        raise HTTPException(status_code=422, detail="mode 只能是 offline 或 agent")
    try:
        filename, extracted_text = await read_and_extract_upload(
            file,
            max_bytes=settings.max_upload_bytes,
            timeout_seconds=settings.document_parse_timeout_seconds,
        )
    except UploadValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    run = AgentRun(
        filename=filename,
        question=question,
        extracted_text=extracted_text,
        mode=mode,
        as_of_date=as_of_date,
        checkpoint_thread_id=f"legal-run-{uuid4()}",
        trace_id=request.state.trace_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return AgentRunCreated(
        run_id=run.id,
        status="queued",
        as_of_date=run.as_of_date,
        trace_id=run.trace_id or "",
        status_url=f"/api/v1/runs/{run.id}",
        report_url=f"/api/v1/runs/{run.id}/report",
        monitoring_url=f"/api/v1/runs/{run.id}/monitoring",
    )


@app.get("/api/v1/runs/{run_id}", response_model=AgentRunStatus)
def get_agent_run(run_id: int, db: Session = Depends(get_db)) -> AgentRunStatus:
    run = _get_agent_run_or_404(db, run_id)
    if run.model_name and run.model_name != "offline-template":
        execution_engine = "llm"
    elif run.status in {"queued", "analyzing"} and not run.facts:
        execution_engine = "pending"
    elif run.mode == "agent":
        execution_engine = "fallback"
    else:
        execution_engine = "rules"
    return AgentRunStatus(
        run_id=run.id,
        status=run.status,
        current_node=run.current_node,
        progress=run.progress,
        retry_count=run.retry_count,
        clarification_round=run.clarification_round,
        state_version=run.state_version,
        current_report_version=run.current_report_version,
        approved_report_version=run.approved_report_version,
        pending_action_url=(
            f"/api/v1/runs/{run.id}/pending-action"
            if run.status in {"waiting_for_user", "waiting_for_approval"}
            else None
        ),
        mode=run.mode,
        as_of_date=run.as_of_date,
        execution_engine=execution_engine,
        model=run.model_name,
        trace_id=run.trace_id or "",
        monitoring_url=f"/api/v1/runs/{run.id}/monitoring",
        total_duration_ms=run.total_duration_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        fallback_count=run.fallback_count,
        facts=CaseFacts.model_validate(run.facts) if run.facts else None,
        traces=run.node_traces or [],
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@app.post("/api/v1/runs/{run_id}/retry", response_model=AgentRunCreated, status_code=202)
def retry_agent_run(
    run_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentRunCreated:
    previous = _get_agent_run_or_404(db, run_id)
    if previous.status != "failed":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试")
    run = AgentRun(
        filename=previous.filename,
        question=previous.question,
        extracted_text=previous.extracted_text,
        mode=previous.mode,
        as_of_date=previous.as_of_date,
        checkpoint_thread_id=f"legal-run-{uuid4()}",
        trace_id=request.state.trace_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return AgentRunCreated(
        run_id=run.id,
        status="queued",
        as_of_date=run.as_of_date,
        trace_id=run.trace_id or "",
        status_url=f"/api/v1/runs/{run.id}",
        report_url=f"/api/v1/runs/{run.id}/report",
        monitoring_url=f"/api/v1/runs/{run.id}/monitoring",
    )


@app.get(
    "/api/v1/monitoring/overview",
    response_model=MonitoringOverview,
    tags=["运行监控"],
)
def get_monitoring_overview(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> MonitoringOverview:
    return build_monitoring_overview(db, days)


@app.get(
    "/api/v1/runs/{run_id}/monitoring",
    response_model=RunMonitoringDetail,
    tags=["运行监控"],
)
def get_run_monitoring(
    run_id: int,
    db: Session = Depends(get_db),
) -> RunMonitoringDetail:
    run = _get_agent_run_or_404(db, run_id)
    detail = build_run_monitoring(db, run)
    if detail is None:
        raise HTTPException(status_code=404, detail="该运行没有可观测性数据")
    return detail


@app.get("/api/v1/runs/{run_id}/pending-action", response_model=PendingActionResponse)
def get_agent_run_pending_action(
    run_id: int,
    db: Session = Depends(get_db),
) -> PendingActionResponse:
    run = _get_agent_run_or_404(db, run_id)
    action: ClarificationPendingAction | ApprovalPendingAction | None = None
    if run.status == "waiting_for_user":
        clarification = db.scalar(
            select(AgentClarification)
            .where(
                AgentClarification.run_id == run_id,
                AgentClarification.status == "pending",
            )
            .order_by(AgentClarification.round_number.desc())
        )
        if clarification is not None:
            action = ClarificationPendingAction(
                action_id=clarification.id,
                round=clarification.round_number,
                max_rounds=settings.max_clarification_rounds,
                questions=[
                    ClarificationQuestion.model_validate(question) for question in clarification.questions
                ],
            )
    elif run.status == "waiting_for_approval":
        row = db.execute(
            select(AgentApproval, ReportVersion)
            .join(ReportVersion, ReportVersion.id == AgentApproval.report_version_id)
            .where(
                AgentApproval.run_id == run_id,
                AgentApproval.status == "pending",
            )
            .order_by(AgentApproval.round_number.desc())
        ).first()
        if row is not None:
            approval, version = row
            action = ApprovalPendingAction(
                action_id=approval.id,
                report_version=version.version_number,
                report_version_id=version.id,
                title=version.title,
                change_summary=version.change_summary,
            )
    return PendingActionResponse(
        run_id=run.id,
        status=run.status,
        state_version=run.state_version,
        action=action,
    )


@app.post(
    "/api/v1/runs/{run_id}/clarifications",
    response_model=ClarificationSubmissionResponse,
    status_code=202,
)
def submit_agent_run_clarification(
    run_id: int,
    payload: ClarificationSubmission,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=200,
    ),
    db: Session = Depends(get_db),
) -> ClarificationSubmissionResponse:
    run = _get_agent_run_or_404(db, run_id)
    replayed = db.scalar(
        select(AgentClarification).where(
            AgentClarification.run_id == run_id,
            AgentClarification.idempotency_key == idempotency_key,
        )
    )
    if replayed is not None:
        return ClarificationSubmissionResponse(
            run_id=run.id,
            status=run.status,
            state_version=run.state_version,
            replayed=True,
            status_url=f"/api/v1/runs/{run.id}",
            message="相同幂等键的回答已经受理，本次未重复恢复工作流。",
        )
    if run.status != "waiting_for_user":
        raise HTTPException(status_code=409, detail="任务当前不在等待用户回答状态")
    clarification = db.scalar(
        select(AgentClarification).where(
            AgentClarification.run_id == run_id,
            AgentClarification.status == "pending",
        )
    )
    if clarification is None:
        raise HTTPException(status_code=409, detail="未找到当前任务的待回答问题")
    if payload.expected_state_version != run.state_version:
        raise HTTPException(
            status_code=409,
            detail=f"任务状态已变化，请刷新后重试；当前版本为 {run.state_version}",
        )
    expected_question_ids = {item["question_id"] for item in clarification.questions}
    submitted_question_ids = {item.question_id for item in payload.answers}
    if submitted_question_ids != expected_question_ids:
        missing_ids = sorted(expected_question_ids - submitted_question_ids)
        unknown_ids = sorted(submitted_question_ids - expected_question_ids)
        details = []
        if missing_ids:
            details.append(f"缺少回答：{', '.join(missing_ids)}")
        if unknown_ids:
            details.append(f"未知问题：{', '.join(unknown_ids)}")
        raise HTTPException(status_code=422, detail="；".join(details))

    result = db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.status == "waiting_for_user",
            AgentRun.state_version == payload.expected_state_version,
        )
        .values(
            status="resuming",
            current_node="clarify_user",
            state_version=AgentRun.state_version + 1,
            error_code=None,
            error_message=None,
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="回答已被其他请求处理，请刷新任务状态")
    clarification.status = "answered"
    clarification.answers = [answer.model_dump() for answer in payload.answers]
    clarification.idempotency_key = idempotency_key
    clarification.answered_state_version = payload.expected_state_version + 1
    clarification.answered_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return ClarificationSubmissionResponse(
        run_id=run.id,
        status="resuming",
        state_version=run.state_version,
        status_url=f"/api/v1/runs/{run.id}",
        message="回答已保存，Agent 正在从持久化 checkpoint 恢复。",
    )


@app.post(
    "/api/v1/runs/{run_id}/approvals",
    response_model=ApprovalSubmissionResponse,
    status_code=202,
)
def submit_agent_run_approval(
    run_id: int,
    payload: ApprovalSubmission,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=200,
    ),
    db: Session = Depends(get_db),
) -> ApprovalSubmissionResponse:
    run = _get_agent_run_or_404(db, run_id)
    replayed = db.scalar(
        select(AgentApproval).where(
            AgentApproval.run_id == run_id,
            AgentApproval.idempotency_key == idempotency_key,
        )
    )
    if replayed is not None and replayed.action is not None:
        version = db.get(ReportVersion, replayed.report_version_id)
        return ApprovalSubmissionResponse(
            run_id=run.id,
            action=cast(ApprovalAction, replayed.action),
            status=run.status,
            state_version=run.state_version,
            report_version=version.version_number if version else replayed.round_number,
            replayed=True,
            status_url=f"/api/v1/runs/{run.id}",
            message="相同幂等键的审批已经受理，本次未重复恢复工作流。",
        )
    if run.status != "waiting_for_approval":
        raise HTTPException(status_code=409, detail="任务当前不在等待人工审批状态")
    if payload.action in {"request_changes", "reject"} and not payload.comment:
        raise HTTPException(status_code=422, detail="要求修改或驳回时必须填写审批意见")
    row = db.execute(
        select(AgentApproval, ReportVersion)
        .join(ReportVersion, ReportVersion.id == AgentApproval.report_version_id)
        .where(
            AgentApproval.run_id == run_id,
            AgentApproval.status == "pending",
        )
        .order_by(AgentApproval.round_number.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=409, detail="未找到当前任务的待审批报告")
    approval, version = row
    if payload.expected_state_version != run.state_version:
        raise HTTPException(
            status_code=409,
            detail=f"任务状态已变化，请刷新后重试；当前版本为 {run.state_version}",
        )
    next_status = "revising" if payload.action == "request_changes" else "resuming"
    result = db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.status == "waiting_for_approval",
            AgentRun.state_version == payload.expected_state_version,
        )
        .values(
            status=next_status,
            current_node="approve_report",
            state_version=AgentRun.state_version + 1,
            error_code=None,
            error_message=None,
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="报告已被其他请求审批，请刷新任务状态")
    approval.status = {
        "approve": "approved",
        "request_changes": "changes_requested",
        "reject": "rejected",
    }[payload.action]
    approval.action = payload.action
    approval.comment = payload.comment
    approval.reviewer = payload.reviewer
    approval.idempotency_key = idempotency_key
    approval.decided_state_version = payload.expected_state_version + 1
    approval.decided_at = datetime.now(UTC)
    if payload.action == "request_changes":
        version.status = "superseded"
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return ApprovalSubmissionResponse(
        run_id=run.id,
        action=payload.action,
        status=next_status,
        state_version=run.state_version,
        report_version=version.version_number,
        status_url=f"/api/v1/runs/{run.id}",
        message={
            "approve": "审批已通过，正在发布批准版本。",
            "request_changes": "修改意见已保存，Agent 正在生成新版本。",
            "reject": "驳回意见已保存，正在终止本次报告。",
        }[payload.action],
    )


@app.get("/api/v1/runs/{run_id}/citations", response_model=list[ReviewedCitation])
def get_agent_run_citations(run_id: int, db: Session = Depends(get_db)) -> list[ReviewedCitation]:
    _get_agent_run_or_404(db, run_id)
    return _get_run_citations(db, run_id)


@app.get("/api/v1/runs/{run_id}/report", response_model=ReportResponse)
def get_agent_run_report(run_id: int, db: Session = Depends(get_db)) -> ReportResponse:
    run = _get_agent_run_or_404(db, run_id)
    version = _get_report_version(db, run_id)
    if version is not None:
        return ReportResponse(
            run_id=run.id,
            as_of_date=run.as_of_date,
            version_number=version.version_number,
            approval_status=cast(ReportVersionStatus, version.status),
            is_final=version.status == "approved",
            title=version.title,
            markdown=version.markdown,
            facts=CaseFacts.model_validate(version.facts_snapshot),
            evidence_gaps=run.evidence_gaps or [],
            citations=_version_citations(version),
            model=run.model_name,
        )
    if run.status != "completed" or not run.report_markdown or not run.facts:
        raise HTTPException(status_code=409, detail="任务尚未生成可用报告")
    return ReportResponse(
        run_id=run.id,
        as_of_date=run.as_of_date,
        version_number=run.approved_report_version or run.current_report_version or 1,
        approval_status="approved",
        is_final=True,
        title=run.report_title or "法律分析报告",
        markdown=run.report_markdown,
        facts=CaseFacts.model_validate(run.facts),
        evidence_gaps=run.evidence_gaps or [],
        citations=_get_run_citations(db, run.id),
        model=run.model_name,
    )


@app.get(
    "/api/v1/runs/{run_id}/report-versions",
    response_model=list[ReportVersionSummary],
)
def list_agent_run_report_versions(
    run_id: int,
    db: Session = Depends(get_db),
) -> list[ReportVersionSummary]:
    _get_agent_run_or_404(db, run_id)
    versions = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.run_id == run_id)
        .order_by(ReportVersion.version_number.desc())
    ).all()
    return [
        ReportVersionSummary(
            version_number=version.version_number,
            status=cast(ReportVersionStatus, version.status),
            title=version.title,
            change_summary=version.change_summary,
            created_at=version.created_at,
            approved_at=version.approved_at,
        )
        for version in versions
    ]


@app.get(
    "/api/v1/runs/{run_id}/report-versions/{version_number}",
    response_model=ReportVersionDetail,
)
def get_agent_run_report_version(
    run_id: int,
    version_number: int,
    db: Session = Depends(get_db),
) -> ReportVersionDetail:
    _get_agent_run_or_404(db, run_id)
    version = _get_report_version(db, run_id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail="未找到指定报告版本")
    previous = _get_report_version(db, run_id, version_number - 1)
    return ReportVersionDetail(
        version_number=version.version_number,
        status=cast(ReportVersionStatus, version.status),
        title=version.title,
        change_summary=version.change_summary,
        created_at=version.created_at,
        approved_at=version.approved_at,
        markdown=version.markdown,
        facts=CaseFacts.model_validate(version.facts_snapshot),
        citations=_version_citations(version),
        diff_from_previous=_version_diff(previous, version),
    )


@app.get("/api/v1/runs/{run_id}/export")
def export_agent_run_report(
    run_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|pdf)$"),
    db: Session = Depends(get_db),
) -> Response:
    run = _get_agent_run_or_404(db, run_id)
    version = db.scalar(
        select(ReportVersion).where(
            ReportVersion.run_id == run_id,
            ReportVersion.status == "approved",
        )
    )
    if version is not None:
        markdown = version.markdown
        title = version.title
        version_suffix = f"-v{version.version_number}"
    elif run.status == "completed" and not db.scalar(
        select(ReportVersion.id).where(ReportVersion.run_id == run_id)
    ):
        # Pre-1.0 reports were already exposed as final; keep their old downloads working.
        markdown = run.report_markdown or ""
        title = run.report_title or "法律分析报告"
        version_suffix = ""
    else:
        raise HTTPException(status_code=409, detail="报告尚未通过人工审批，不能导出最终版本")
    if not markdown:
        raise HTTPException(status_code=409, detail="任务尚未生成可导出的报告")
    if format == "pdf":
        content = markdown_to_pdf(markdown, title)
        media_type = "application/pdf"
        extension = "pdf"
    else:
        content = markdown.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="legal-report-{run.id}{version_suffix}.{extension}"'
            )
        },
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
