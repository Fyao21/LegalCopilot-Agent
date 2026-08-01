import logging
from dataclasses import replace
from datetime import date

from sqlalchemy.orm import Session

from app.services.embedding_provider import (
    EmbeddingProviderError,
    HashEmbeddingProvider,
    get_embedding_provider,
)
from app.services.mixed_retriever import RetrievalResult, retrieve_articles_mixed

logger = logging.getLogger("legal_copilot.retrieval")


def retrieve_articles_configured(
    db: Session,
    query: str,
    limit: int = 5,
    *,
    force_offline: bool = False,
    as_of_date: date | None = None,
) -> RetrievalResult:
    """Use the configured provider, retry transient failures, then expose any hash fallback."""
    try:
        provider = get_embedding_provider(force_offline=force_offline)
    except EmbeddingProviderError as error:
        logger.warning("embedding_provider_configuration_fallback: %s", error)
        fallback = retrieve_articles_mixed(
            db,
            query,
            HashEmbeddingProvider(),
            limit,
            as_of_date=as_of_date,
        )
        return RetrievalResult(
            citations=fallback.citations,
            provider=fallback.provider,
            model=fallback.model,
            as_of_date=fallback.as_of_date,
            fallback_reason=f"Embedding 配置不可用：{error}",
            attempted_provider="configuration",
            attempted_model=None,
            input_tokens=0,
            retry_count=0,
            embedding_duration_ms=fallback.embedding_duration_ms,
            db_search_duration_ms=fallback.db_search_duration_ms,
        )

    if isinstance(provider, HashEmbeddingProvider):
        return retrieve_articles_mixed(db, query, provider, limit, as_of_date=as_of_date)

    last_error: EmbeddingProviderError | None = None
    for attempt in range(1, 3):
        try:
            result = retrieve_articles_mixed(db, query, provider, limit, as_of_date=as_of_date)
            usage = provider.usage_snapshot()
            return replace(
                result,
                input_tokens=usage.input_tokens,
                retry_count=usage.retry_count,
            )
        except EmbeddingProviderError as error:
            last_error = error
            db.rollback()
            logger.warning(
                "embedding_provider_request_retry: provider=%s model=%s attempt=%s error=%s",
                provider.provider_name,
                provider.model_name,
                attempt,
                error,
            )

    assert last_error is not None
    logger.warning(
        "embedding_provider_request_fallback: provider=%s model=%s attempts=2 error=%s",
        provider.provider_name,
        provider.model_name,
        last_error,
    )
    fallback = retrieve_articles_mixed(
        db,
        query,
        HashEmbeddingProvider(),
        limit,
        as_of_date=as_of_date,
    )
    return RetrievalResult(
        citations=fallback.citations,
        provider=fallback.provider,
        model=fallback.model,
        as_of_date=fallback.as_of_date,
        fallback_reason=(f"{provider.provider_name}/{provider.model_name} 连续 2 次请求失败：{last_error}"),
        attempted_provider=provider.provider_name,
        attempted_model=provider.model_name,
        input_tokens=provider.usage_snapshot().input_tokens,
        retry_count=provider.usage_snapshot().retry_count,
        embedding_duration_ms=fallback.embedding_duration_ms,
        db_search_duration_ms=fallback.db_search_duration_ms,
    )
