import json
import re
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClientError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class OpenAICompatibleLLM:
    """Minimal OpenAI-compatible JSON client with bounded retry and Schema validation."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float = 60):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema: type[SchemaT]) -> SchemaT:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        last_error: LLMClientError | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                if response.status_code in {401, 403}:
                    raise LLMClientError("LLM_AUTH_FAILED", "模型服务认证失败，请检查 API Key")
                if response.status_code == 429:
                    raise LLMClientError("LLM_RATE_LIMITED", "模型服务请求过于频繁", retryable=True)
                if response.status_code >= 500:
                    raise LLMClientError(
                        "LLM_PROVIDER_ERROR", f"模型服务错误：HTTP {response.status_code}", retryable=True
                    )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                data = json.loads(_extract_json(content))
                return schema.model_validate(data)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = LLMClientError("LLM_TIMEOUT", f"模型请求失败：{error}", retryable=True)
            except (KeyError, json.JSONDecodeError, ValidationError) as error:
                last_error = LLMClientError("LLM_INVALID_OUTPUT", f"模型结构化输出校验失败：{error}")
                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": "上一次输出无法通过 JSON Schema 校验。请重新返回完整、合法的 JSON 对象，不要解释。",
                        }
                    )
                    continue
                raise last_error from error
            except httpx.HTTPStatusError as error:
                raise LLMClientError(
                    "LLM_HTTP_ERROR", f"模型请求失败：{error.response.status_code}"
                ) from error
            except LLMClientError as error:
                last_error = error
                if not error.retryable:
                    raise
            if attempt == 0:
                time.sleep(0.5)
        assert last_error is not None
        raise last_error


def _extract_json(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def get_llm_client() -> OpenAICompatibleLLM | None:
    settings = get_settings()
    if settings.offline_mode or not settings.llm_api_key:
        return None
    return OpenAICompatibleLLM(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
