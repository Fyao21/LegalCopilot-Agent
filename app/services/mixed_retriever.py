import re
import time
from dataclasses import dataclass
from datetime import date
from typing import cast

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ArticleEmbedding, LawVersion, LegalArticle
from app.schemas import Citation, LawEffectStatus
from app.services.embedding_index import ensure_article_embeddings
from app.services.embedding_provider import EmbeddingProvider
from app.services.embeddings import cosine_similarity, tokenize


@dataclass(frozen=True)
class RetrievalResult:
    citations: list[Citation]
    provider: str
    model: str
    as_of_date: date
    fallback_reason: str | None = None
    attempted_provider: str | None = None
    attempted_model: str | None = None
    input_tokens: int = 0
    retry_count: int = 0
    embedding_duration_ms: int = 0
    db_search_duration_ms: int = 0


def _keyword_score(query: str, article: LegalArticle) -> float:
    query_tokens = set(tokenize(query))
    article_tokens = set(tokenize(f"{article.law_name}{article.article_number}{article.content}"))
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens & article_tokens) / len(query_tokens)
    exact_bonus = 0.0
    compact_query = re.sub(r"\s+", "", query)
    if article.article_number in compact_query:
        exact_bonus += 0.4
    if article.law_name in compact_query:
        exact_bonus += 0.2
    return min(1.0, overlap + exact_bonus)


def retrieve_articles_mixed(
    db: Session,
    query: str,
    provider: EmbeddingProvider,
    limit: int = 5,
    as_of_date: date | None = None,
) -> RetrievalResult:
    target_date = as_of_date or date.today()
    embedding_started = time.perf_counter()
    ensure_article_embeddings(db, provider)
    query_vector = provider.embed_query(query)
    embedding_duration_ms = max(0, round((time.perf_counter() - embedding_started) * 1000))
    search_started = time.perf_counter()
    article_rows = db.execute(
        select(LegalArticle, LawVersion)
        .outerjoin(LawVersion, LegalArticle.law_version_id == LawVersion.id)
        .where(
            or_(
                LegalArticle.law_version_id.is_(None),
                and_(
                    LawVersion.effective_from <= target_date,
                    or_(
                        LawVersion.effective_to.is_(None),
                        LawVersion.effective_to > target_date,
                    ),
                ),
            )
        )
    ).all()
    embedding_rows = db.scalars(
        select(ArticleEmbedding).where(
            ArticleEmbedding.provider == provider.provider_name,
            ArticleEmbedding.model == provider.model_name,
        )
    ).all()
    vectors = {row.article_id: row.vector for row in embedding_rows}
    settings = get_settings()
    scored: list[tuple[LegalArticle, LawVersion | None, float, float, float]] = []
    for article, version in article_rows:
        vector = vectors.get(article.id)
        if vector is None or len(vector) != len(query_vector):
            continue
        keyword = _keyword_score(query, article)
        semantic = max(0.0, cosine_similarity(query_vector, vector))
        combined = settings.retrieval_keyword_weight * keyword + settings.retrieval_semantic_weight * semantic
        scored.append((article, version, combined, keyword, semantic))
    scored.sort(key=lambda item: item[2], reverse=True)
    citations = [
        Citation(
            article_id=article.id,
            law_name=article.law_name,
            article_number=article.article_number,
            excerpt=article.content,
            source=article.source,
            score=round(combined, 4),
            keyword_score=round(keyword, 4),
            semantic_score=round(semantic, 4),
            law_id=version.law_id if version else None,
            law_version_id=version.id if version else None,
            version_label=version.version_label if version else "未标注版本",
            effect_status=cast(LawEffectStatus, version.status) if version else "legacy",
            effective_from=version.effective_from if version else None,
            effective_to=version.effective_to if version else None,
        )
        for article, version, combined, keyword, semantic in scored[:limit]
    ]
    db_search_duration_ms = max(0, round((time.perf_counter() - search_started) * 1000))
    usage = provider.usage_snapshot()
    return RetrievalResult(
        citations=citations,
        provider=provider.provider_name,
        model=provider.model_name,
        as_of_date=target_date,
        attempted_provider=provider.provider_name,
        attempted_model=provider.model_name,
        input_tokens=usage.input_tokens,
        retry_count=usage.retry_count,
        embedding_duration_ms=embedding_duration_ms,
        db_search_duration_ms=db_search_duration_ms,
    )
