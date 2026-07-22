from abc import ABC, abstractmethod

import httpx

from app.config import get_settings
from app.services.embeddings import embed


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashEmbeddingProvider(EmbeddingProvider):
    provider_name = "hash"
    model_name = "chinese-bigram-sha256-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [embed(text) for text in texts]


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model_name: str, timeout_seconds: float):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model_name, "input": texts},
                )
            if response.status_code in {401, 403}:
                raise EmbeddingProviderError("Embedding 服务认证失败")
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [row["embedding"] for row in rows]
            if len(vectors) != len(texts):
                raise EmbeddingProviderError("Embedding 返回数量与输入数量不一致")
            if vectors and any(len(vector) != len(vectors[0]) for vector in vectors):
                raise EmbeddingProviderError("Embedding 返回向量维度不一致")
            return vectors
        except (httpx.HTTPError, KeyError, TypeError) as error:
            raise EmbeddingProviderError(f"Embedding 请求失败：{error}") from error


def get_embedding_provider(force_offline: bool = False) -> EmbeddingProvider:
    settings = get_settings()
    if force_offline or settings.offline_mode or settings.embedding_provider == "hash":
        return HashEmbeddingProvider()
    if not settings.embedding_api_key:
        raise EmbeddingProviderError("未配置 EMBEDDING_API_KEY")
    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model_name=settings.embedding_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
