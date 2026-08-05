"""Check the configured Embedding provider with one short request without printing secrets."""

# ruff: noqa: E402

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embedding_provider import (
    EmbeddingProviderError,
    HashEmbeddingProvider,
    get_embedding_provider,
)

if __name__ == "__main__":
    try:
        provider = get_embedding_provider()
        vector = provider.embed_query("公司拖欠工资并且没有签订书面劳动合同")
    except EmbeddingProviderError as error:
        print(f"embedding_check=failed error={error}")
        raise SystemExit(1) from error

    mode = "offline-hash" if isinstance(provider, HashEmbeddingProvider) else "online"
    nonzero = sum(abs(value) > 1e-12 for value in vector)
    print(
        f"embedding_check=ok mode={mode} provider={provider.provider_name} "
        f"model={provider.model_name} dimensions={len(vector)} nonzero={nonzero}"
    )
