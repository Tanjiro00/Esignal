from __future__ import annotations

import base64
import struct
import time
from dataclasses import dataclass
from typing import Any

import httpx


class EmbeddingProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class EncodedEmbedding:
    index: int
    value: str


@dataclass(frozen=True)
class EmbeddingBatchResult:
    embeddings: tuple[EncodedEmbedding, ...]
    model: str
    input_tokens: int


class OpenAIEmbeddingProvider:
    """Small typed adapter around the server-side OpenAI embeddings endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 256,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 90,
        retry_attempts: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = max(1, retry_attempts)
        self._client = client

    def embed(self, texts: list[str]) -> EmbeddingBatchResult:
        if not self._api_key:
            raise EmbeddingProviderError("not_configured", "OpenAI API key is not configured.")
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embedding inputs must be non-empty")
        if len(texts) > 2_048:
            raise ValueError("embedding request cannot contain more than 2048 inputs")

        body: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimensions,
            "encoding_format": "base64",
        }
        last_error: EmbeddingProviderError | None = None
        for attempt in range(self._retry_attempts):
            try:
                client = self._client
                if client is None:
                    response = httpx.post(
                        f"{self._base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                        timeout=self._timeout_seconds,
                    )
                else:
                    response = client.post(
                        f"{self._base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                        timeout=self._timeout_seconds,
                    )
                if response.status_code >= 400:
                    retryable = response.status_code in {408, 409, 429, 500, 502, 503, 504}
                    last_error = EmbeddingProviderError(
                        f"http_{response.status_code}",
                        f"OpenAI embeddings API returned HTTP {response.status_code}.",
                        retryable=retryable,
                    )
                    if retryable and attempt + 1 < self._retry_attempts:
                        time.sleep(min(2**attempt, 4))
                        continue
                    raise last_error
                return self._parse(response.json(), expected=len(texts))
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = EmbeddingProviderError(
                    type(error).__name__,
                    "OpenAI embedding request failed before a response was received.",
                    retryable=True,
                )
                if attempt + 1 >= self._retry_attempts:
                    raise last_error from error
                time.sleep(min(2**attempt, 4))
        if last_error is not None:
            raise last_error
        raise EmbeddingProviderError("unknown", "OpenAI embedding request failed.")

    def _parse(self, payload: object, *, expected: int) -> EmbeddingBatchResult:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise EmbeddingProviderError("invalid_response", "Embedding response has no data list.")
        rows: list[EncodedEmbedding] = []
        for raw in payload["data"]:
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("index"), int)
                or not isinstance(raw.get("embedding"), str)
            ):
                raise EmbeddingProviderError(
                    "invalid_embedding",
                    "Embedding response contains an invalid row.",
                )
            rows.append(EncodedEmbedding(index=raw["index"], value=raw["embedding"]))
        ordered = tuple(sorted(rows, key=lambda item: item.index))
        if len(ordered) != expected or tuple(item.index for item in ordered) != tuple(
            range(expected)
        ):
            raise EmbeddingProviderError(
                "embedding_count_mismatch",
                "Embedding response does not match the requested input order.",
            )
        usage = payload.get("usage")
        token_value = (
            usage.get("prompt_tokens", usage.get("input_tokens"))
            if isinstance(usage, dict)
            else None
        )
        input_tokens = token_value if isinstance(token_value, int) else 0
        return EmbeddingBatchResult(
            embeddings=ordered,
            model=str(payload.get("model") or self.model),
            input_tokens=input_tokens,
        )


def decode_embedding(value: str, *, dimensions: int) -> tuple[float, ...]:
    raw = base64.b64decode(value, validate=True)
    if len(raw) != dimensions * 4:
        raise ValueError("encoded embedding has an unexpected byte length")
    return struct.unpack(f"<{dimensions}f", raw)


__all__ = [
    "EmbeddingBatchResult",
    "EmbeddingProviderError",
    "EncodedEmbedding",
    "OpenAIEmbeddingProvider",
    "decode_embedding",
]
