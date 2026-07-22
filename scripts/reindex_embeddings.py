"""为当前法规库生成配置指定的 Embedding，可重复安全执行。"""
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.embedding_index import ensure_article_embeddings  # noqa: E402
from app.services.embedding_provider import get_embedding_provider  # noqa: E402
from app.services.seed import seed_sample_laws  # noqa: E402


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_sample_laws(db)
        provider = get_embedding_provider()
        count = ensure_article_embeddings(db, provider)
        print(f"provider={provider.provider_name} model={provider.model_name} updated={count}")
