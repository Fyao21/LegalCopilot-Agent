import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LegalArticle
from app.services.embeddings import embed


def seed_sample_laws(db: Session) -> int:
    if db.scalar(select(func.count()).select_from(LegalArticle)):
        return 0
    records = []
    with get_settings().sample_laws_file.open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                record = json.loads(line)
                records.append(
                    LegalArticle(
                        law_name=record["law_name"],
                        article_number=record["article_number"],
                        content=record["content"],
                        source=record["source"],
                        embedding=embed(record["content"]),
                    )
                )
    db.add_all(records)
    db.commit()
    return len(records)
