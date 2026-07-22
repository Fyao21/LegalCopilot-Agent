from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LegalArticle
from app.schemas import Citation
from app.services.embeddings import cosine_similarity, embed


def retrieve_articles(db: Session, query: str, limit: int = 5) -> list[Citation]:
    query_vector = embed(query)
    articles = db.scalars(select(LegalArticle)).all()
    ranked = sorted(
        ((article, cosine_similarity(query_vector, article.embedding)) for article in articles),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]
    return [
        Citation(
            article_id=article.id,
            law_name=article.law_name,
            article_number=article.article_number,
            excerpt=article.content,
            source=article.source,
            score=round(score, 4),
        )
        for article, score in ranked
    ]
