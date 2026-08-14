from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class LLMProviderResult:
    output: BaseModel
    response_id: str
    model: str
    usage: dict[str, int]
    latency_ms: int


class LLMProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult: ...


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 45,
        reasoning_effort: str = "low",
        max_output_tokens: int = 4_000,
        retry_attempts: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._retry_attempts = max(1, retry_attempts)
        self._client = client

    @staticmethod
    def _output_text(data: dict[str, object]) -> str:
        output = data.get("output")
        if not isinstance(output, list):
            raise LLMProviderError("missing_output", "The model response has no output items.")
        refusals: list[str] = []
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(str(part["text"]))
                if part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                    refusals.append(str(part["refusal"]))
        if refusals:
            raise LLMProviderError("refusal", "The model refused the structured synthesis.")
        if not texts:
            raise LLMProviderError("missing_output_text", "The model returned no structured text.")
        return "".join(texts)

    @staticmethod
    def _usage(data: dict[str, object]) -> dict[str, int]:
        raw = data.get("usage")
        if not isinstance(raw, dict):
            return {}
        fields = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_output_tokens",
        )
        return {field: int(raw[field]) for field in fields if isinstance(raw.get(field), int)}

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult:
        if not self._api_key:
            raise LLMProviderError("not_configured", "OpenAI API key is not configured.")
        request_body: dict[str, object] = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "developer", "content": developer_prompt},
                {"role": "user", "content": payload},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": task.replace("-", "_")[:64],
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
                "verbosity": "low",
            },
            "reasoning": {"effort": self._reasoning_effort},
            "max_output_tokens": self._max_output_tokens,
        }
        started = time.monotonic()
        last_error: LLMProviderError | None = None
        for attempt in range(self._retry_attempts):
            try:
                if self._client is None:
                    response = httpx.post(
                        f"{self._base_url}/responses",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_body,
                        timeout=self._timeout_seconds,
                    )
                else:
                    response = self._client.post(
                        f"{self._base_url}/responses",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_body,
                        timeout=self._timeout_seconds,
                    )
                if response.status_code >= 400:
                    retryable = response.status_code in {408, 409, 429, 500, 502, 503, 504}
                    last_error = LLMProviderError(
                        f"http_{response.status_code}",
                        f"OpenAI Responses API returned HTTP {response.status_code}.",
                        retryable=retryable,
                    )
                    if retryable and attempt + 1 < self._retry_attempts:
                        continue
                    raise last_error
                raw_data = response.json()
                if not isinstance(raw_data, dict):
                    raise LLMProviderError(
                        "invalid_response",
                        "OpenAI Responses API returned a non-object payload.",
                    )
                data = {str(key): value for key, value in raw_data.items()}
                status = data.get("status")
                if status not in {None, "completed"}:
                    raise LLMProviderError(
                        f"response_{status}",
                        f"OpenAI response did not complete: {status}.",
                        retryable=status in {"queued", "in_progress"},
                    )
                try:
                    parsed = response_model.model_validate_json(self._output_text(data))
                except ValidationError as error:
                    raise LLMProviderError(
                        "schema_validation",
                        "OpenAI output failed application schema validation.",
                    ) from error
                return LLMProviderResult(
                    output=parsed,
                    response_id=str(data.get("id", "")),
                    model=str(data.get("model", self.model)),
                    usage=self._usage(data),
                    latency_ms=round((time.monotonic() - started) * 1_000),
                )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = LLMProviderError(
                    type(error).__name__,
                    "OpenAI request failed before a response was received.",
                    retryable=True,
                )
                if attempt + 1 >= self._retry_attempts:
                    raise last_error from error
        if last_error is not None:
            raise last_error
        raise LLMProviderError("unknown", "OpenAI request failed.")
