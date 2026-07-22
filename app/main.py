from contextlib import asynccontextmanager
import json
import logging
import time
from uuid import uuid4

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.migrations import ensure_runtime_schema
from app.models import AgentRun, AgentRunCitation, CaseRun, LegalArticle, RetrievalLog
from app.schemas import (
    AgentRunCreated,
    AgentRunStatus,
    CaseAnalysisResponse,
    Citation,
    HealthResponse,
    LegalArticleDetail,
    ReportResponse,
    ReviewedCitation,
    SearchRequest,
)
from app.services.case_analyzer import analyze_case
from app.services.embedding_index import ensure_article_embeddings
from app.services.embedding_provider import get_embedding_provider
from app.services.mixed_retriever import retrieve_articles_mixed
from app.services.report_export import markdown_to_pdf
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
        ensure_article_embeddings(db, get_embedding_provider(force_offline=True))
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="可追溯法律检索与案件要素分析 MVP",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            json.dumps(
                {"event": "request_failed", "request_id": request_id, "method": request.method, "path": request.url.path},
                ensure_ascii=False,
            )
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        json.dumps(
            {
                "event": "request_completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            ensure_ascii=False,
        )
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    count = db.scalar(select(func.count()).select_from(LegalArticle)) or 0
    return HealthResponse(status="ok", article_count=count)


@app.post("/api/v1/articles/search", response_model=list[Citation])
def search_articles(request: SearchRequest, db: Session = Depends(get_db)) -> list[Citation]:
    return retrieve_articles_mixed(db, request.query, get_embedding_provider(force_offline=True), request.limit).citations


@app.get("/api/v1/articles/{article_id}", response_model=LegalArticleDetail)
def get_article(article_id: int, db: Session = Depends(get_db)) -> LegalArticleDetail:
    article = db.get(LegalArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="未找到指定法规条文")
    return LegalArticleDetail(
        article_id=article.id,
        law_name=article.law_name,
        article_number=article.article_number,
        content=article.content,
        source=article.source,
    )


@app.post("/api/v1/cases", response_model=CaseAnalysisResponse, status_code=201)
async def create_case(
    question: str = Form(..., min_length=2, max_length=5000),
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
    )
    db.add(run)
    db.flush()
    query = "\n".join([question, *facts.dispute_focuses, *facts.claims])
    citations = retrieve_articles_mixed(db, query, get_embedding_provider(force_offline=True), settings.top_k).citations
    db.add_all(
        RetrievalLog(case_run_id=run.id, article_id=citation.article_id, score=citation.score)
        for citation in citations
    )
    db.commit()
    return CaseAnalysisResponse(run_id=run.id, facts=facts, citations=citations)


def _get_agent_run_or_404(db: Session, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="未找到指定 Agent 任务")
    return run


def _get_run_citations(db: Session, run_id: int) -> list[ReviewedCitation]:
    rows = db.execute(
        select(AgentRunCitation, LegalArticle)
        .join(LegalArticle, LegalArticle.id == AgentRunCitation.article_id)
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
        )
        for log, article in rows
    ]


@app.post("/api/v1/runs", response_model=AgentRunCreated, status_code=202)
async def create_agent_run(
    background_tasks: BackgroundTasks,
    question: str = Form(..., min_length=2, max_length=5000),
    mode: str = Form(default="offline"),
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
    run = AgentRun(filename=filename, question=question, extracted_text=extracted_text, mode=mode)
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return AgentRunCreated(
        run_id=run.id,
        status="queued",
        status_url=f"/api/v1/runs/{run.id}",
        report_url=f"/api/v1/runs/{run.id}/report",
    )


@app.get("/api/v1/runs/{run_id}", response_model=AgentRunStatus)
def get_agent_run(run_id: int, db: Session = Depends(get_db)) -> AgentRunStatus:
    run = _get_agent_run_or_404(db, run_id)
    return AgentRunStatus(
        run_id=run.id,
        status=run.status,
        current_node=run.current_node,
        progress=run.progress,
        retry_count=run.retry_count,
        mode=run.mode,
        facts=run.facts,
        traces=run.node_traces or [],
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@app.post("/api/v1/runs/{run_id}/retry", response_model=AgentRunCreated, status_code=202)
def retry_agent_run(run_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> AgentRunCreated:
    previous = _get_agent_run_or_404(db, run_id)
    if previous.status != "failed":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试")
    run = AgentRun(
        filename=previous.filename,
        question=previous.question,
        extracted_text=previous.extracted_text,
        mode=previous.mode,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_agent_run_by_id, run.id)
    return AgentRunCreated(
        run_id=run.id,
        status="queued",
        status_url=f"/api/v1/runs/{run.id}",
        report_url=f"/api/v1/runs/{run.id}/report",
    )


@app.get("/api/v1/runs/{run_id}/citations", response_model=list[ReviewedCitation])
def get_agent_run_citations(run_id: int, db: Session = Depends(get_db)) -> list[ReviewedCitation]:
    _get_agent_run_or_404(db, run_id)
    return _get_run_citations(db, run_id)


@app.get("/api/v1/runs/{run_id}/report", response_model=ReportResponse)
def get_agent_run_report(run_id: int, db: Session = Depends(get_db)) -> ReportResponse:
    run = _get_agent_run_or_404(db, run_id)
    if run.status != "completed" or not run.report_markdown or not run.facts:
        raise HTTPException(status_code=409, detail="任务尚未生成可用报告")
    return ReportResponse(
        run_id=run.id,
        title=run.report_title or "法律分析报告",
        markdown=run.report_markdown,
        facts=run.facts,
        evidence_gaps=run.evidence_gaps or [],
        citations=_get_run_citations(db, run.id),
        model=run.model_name,
    )


@app.get("/api/v1/runs/{run_id}/export")
def export_agent_run_report(
    run_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|pdf)$"),
    db: Session = Depends(get_db),
) -> Response:
    run = _get_agent_run_or_404(db, run_id)
    if run.status != "completed" or not run.report_markdown:
        raise HTTPException(status_code=409, detail="任务尚未生成可导出的报告")
    if format == "pdf":
        content = markdown_to_pdf(run.report_markdown, run.report_title or "法律分析报告")
        media_type = "application/pdf"
        extension = "pdf"
    else:
        content = run.report_markdown.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="legal-report-{run.id}.{extension}"'},
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
