import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LegalArticle
from app.services.embeddings import embed


def seed_sample_laws(db: Session) -> int:
    existing_keys = {
        (law_name, article_number)
        for law_name, article_number in db.execute(select(LegalArticle.law_name, LegalArticle.article_number))
    }
    records = []
    with get_settings().sample_laws_file.open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                record = json.loads(line)
                key = (record["law_name"].strip(), record["article_number"].strip())
                if key in existing_keys:
                    continue
                records.append(
                    LegalArticle(
                        law_name=key[0],
                        article_number=key[1],
                        content=record["content"].strip(),
                        source=record["source"].strip(),
                        embedding=embed(record["content"].strip()),
                    )
                )
                existing_keys.add(key)
    if records:
        db.add_all(records)
        db.commit()
    return len(records)
