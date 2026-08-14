import base64
import struct

import httpx
import pytest

from packages.clustering.embedding_provider import (
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    decode_embedding,
)


def _encoded(*values: float) -> str:
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode()


def test_embedding_provider_preserves_response_index_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        payload = {
            "model": "text-embedding-3-small",
            "data": [
                {"index": 1, "embedding": _encoded(0.0, 1.0)},
                {"index": 0, "embedding": _encoded(1.0, 0.0)},
            ],
            "usage": {"prompt_tokens": 8},
        }
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIEmbeddingProvider(
            api_key="secret",
            dimensions=2,
            client=client,
        ).embed(["first", "second"])

    assert [row.index for row in result.embeddings] == [0, 1]
    assert decode_embedding(result.embeddings[0].value, dimensions=2) == (1.0, 0.0)
    assert result.input_tokens == 8


def test_embedding_provider_rejects_mismatched_rows() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": [{"index": 1, "embedding": _encoded(0.0, 1.0)}]},
            )
        )
    ) as client:
        provider = OpenAIEmbeddingProvider(api_key="secret", dimensions=2, client=client)
        with pytest.raises(EmbeddingProviderError, match="input order"):
            provider.embed(["first"])


def test_decode_embedding_checks_dimension() -> None:
    with pytest.raises(ValueError, match="byte length"):
        decode_embedding(_encoded(1.0), dimensions=2)
