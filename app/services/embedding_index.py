import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArticleEmbedding, LegalArticle
from app.services.embedding_provider import EmbeddingProvider


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_article_embeddings(db: Session, provider: EmbeddingProvider) -> int:
    articles = db.scalars(select(LegalArticle).order_by(LegalArticle.id)).all()
    existing = {
        row.article_id: row
        for row in db.scalars(
            select(ArticleEmbedding).where(
                ArticleEmbedding.provider == provider.provider_name,
                ArticleEmbedding.model == provider.model_name,
            )
        ).all()
    }
    pending = [
        article
        for article in articles
        if article.id not in existing or existing[article.id].content_hash != content_hash(article.content)
    ]
    if not pending:
        return 0
    vectors = provider.embed_documents([article.content for article in pending])
    for article, vector in zip(pending, vectors):
        row = existing.get(article.id)
        if row is None:
            row = ArticleEmbedding(
                article_id=article.id, provider=provider.provider_name, model=provider.model_name
            )
            db.add(row)
        row.dimensions = len(vector)
        row.content_hash = content_hash(article.content)
        row.vector = vector
    db.commit()
    return len(pending)
