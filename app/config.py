import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    top_k: int
    embedding_dimensions: int
    sample_laws_file: Path
    offline_mode: bool
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_timeout_seconds: float
    embedding_provider: str
    embedding_api_key: str | None
    embedding_base_url: str
    embedding_model: str
    retrieval_keyword_weight: float
    retrieval_semantic_weight: float
    max_workflow_retries: int
    max_upload_bytes: int
    document_parse_timeout_seconds: float
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    default_db = (PROJECT_ROOT / "data" / "legal_copilot.db").as_posix()
    offline_mode = os.getenv("OFFLINE_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}
    keyword_weight = float(os.getenv("RETRIEVAL_KEYWORD_WEIGHT", "0.35"))
    semantic_weight = float(os.getenv("RETRIEVAL_SEMANTIC_WEIGHT", "0.65"))
    if keyword_weight < 0 or semantic_weight < 0 or keyword_weight + semantic_weight <= 0:
        raise ValueError("检索权重必须为非负数且总和大于 0")
    total_weight = keyword_weight + semantic_weight
    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:3000,http://localhost:3000",
        ).split(",")
        if origin.strip()
    )
    # Accept common OpenAI-compatible names so existing local configurations can be reused.
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None
    embedding_api_key = os.getenv("EMBEDDING_API_KEY") or None
    return Settings(
        app_name=os.getenv("APP_NAME", "律镜 Legal Copilot"),
        database_url=os.getenv("DATABASE_URL") or f"sqlite:///{default_db}",
        top_k=int(os.getenv("TOP_K", "5")),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "384")),
        sample_laws_file=PROJECT_ROOT / "data" / "sample_laws.jsonl",
        offline_mode=offline_mode,
        llm_api_key=llm_api_key,
        llm_base_url=(os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
        llm_model=os.getenv("LLM_MODEL") or os.getenv("MODEL_NAME") or "deepseek-v4-flash",
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower(),
        embedding_api_key=embedding_api_key,
        embedding_base_url=(os.getenv("EMBEDDING_BASE_URL") or "").rstrip("/"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        retrieval_keyword_weight=keyword_weight / total_weight,
        retrieval_semantic_weight=semantic_weight / total_weight,
        max_workflow_retries=max(0, int(os.getenv("MAX_WORKFLOW_RETRIES", "2"))),
        max_upload_bytes=max(1, int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))),
        document_parse_timeout_seconds=max(1.0, float(os.getenv("DOCUMENT_PARSE_TIMEOUT_SECONDS", "15"))),
        cors_origins=cors_origins,
    )
