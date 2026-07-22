import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ArticleEmbedding, LegalArticle
from app.schemas import Citation
from app.services.embedding_index import ensure_article_embeddings
from app.services.embedding_provider import EmbeddingProvider
from app.services.embeddings import cosine_similarity, tokenize


@dataclass(frozen=True)
class RetrievalResult:
    citations: list[Citation]
    provider: str
    model: str


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
) -> RetrievalResult:
    ensure_article_embeddings(db, provider)
    query_vector = provider.embed_query(query)
    articles = db.scalars(select(LegalArticle)).all()
    embedding_rows = db.scalars(
        select(ArticleEmbedding).where(
            ArticleEmbedding.provider == provider.provider_name,
            ArticleEmbedding.model == provider.model_name,
        )
    ).all()
    vectors = {row.article_id: row.vector for row in embedding_rows}
    settings = get_settings()
    scored: list[tuple[LegalArticle, float, float, float]] = []
    for article in articles:
        vector = vectors.get(article.id)
        if vector is None or len(vector) != len(query_vector):
            continue
        keyword = _keyword_score(query, article)
        semantic = max(0.0, cosine_similarity(query_vector, vector))
        combined = settings.retrieval_keyword_weight * keyword + settings.retrieval_semantic_weight * semantic
        scored.append((article, combined, keyword, semantic))
    scored.sort(key=lambda item: item[1], reverse=True)
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
        )
        for article, combined, keyword, semantic in scored[:limit]
    ]
    return RetrievalResult(citations=citations, provider=provider.provider_name, model=provider.model_name)
