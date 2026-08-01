import json
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsageSnapshot:
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    retry_count: int = 0
    last_error_code: str | None = None


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4) if text else 0


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
        self._input_tokens = 0
        self._output_tokens = 0
        self._request_count = 0
        self._retry_count = 0
        self._last_error_code: str | None = None

    def usage_snapshot(self) -> LLMUsageSnapshot:
        return LLMUsageSnapshot(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            request_count=self._request_count,
            retry_count=self._retry_count,
            last_error_code=self._last_error_code,
        )

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
            self._request_count += 1
            if attempt:
                self._retry_count += 1
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
                response_body = response.json()
                content = response_body["choices"][0]["message"]["content"]
                usage = response_body.get("usage") or {}
                self._input_tokens += int(
                    usage.get("prompt_tokens") or _estimate_tokens(json.dumps(messages, ensure_ascii=False))
                )
                self._output_tokens += int(usage.get("completion_tokens") or _estimate_tokens(content))
                data = json.loads(_extract_json(content))
                self._last_error_code = None
                return schema.model_validate(data)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = LLMClientError("LLM_TIMEOUT", f"模型请求失败：{error}", retryable=True)
                self._last_error_code = last_error.code
            except (KeyError, json.JSONDecodeError, ValidationError) as error:
                last_error = LLMClientError("LLM_INVALID_OUTPUT", f"模型结构化输出校验失败：{error}")
                self._last_error_code = last_error.code
                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "上一次输出无法通过 JSON Schema 校验。"
                                f"具体错误：{error}。"
                                f"目标 Schema：{json.dumps(schema.model_json_schema(), ensure_ascii=False)}。"
                                "请修正字段类型并重新返回完整、合法的 JSON 对象，不要解释。"
                            ),
                        }
                    )
                    continue
                raise last_error from error
            except httpx.HTTPStatusError as error:
                self._last_error_code = "LLM_HTTP_ERROR"
                raise LLMClientError(
                    "LLM_HTTP_ERROR", f"模型请求失败：{error.response.status_code}"
                ) from error
            except LLMClientError as error:
                last_error = error
                self._last_error_code = error.code
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
