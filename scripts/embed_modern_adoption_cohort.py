from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.backtest.modern_adoption import load_structural_cohort
from packages.clustering import MicrotopicDocument, infer_microtopic_identity_v7
from packages.clustering.embedding_provider import OpenAIEmbeddingProvider
from packages.clustering.microtopics_v7 import normalize_format_neutral_title

EMBEDDING_DATASET_VERSION = "modern-adoption-title-description-embeddings-v1"


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _embedding_text(title: str, description: str) -> str:
    clean_title = normalize_format_neutral_title(title)
    clean_description = re.sub(r"https?://\S+", " ", description[:600])
    clean_description = " ".join(clean_description.split())
    return f"Title: {clean_title}\nContext: {clean_description[:400]}".strip()


def _candidate(title: str, description: str, video_id: str) -> bool:
    document = MicrotopicDocument(
        id=video_id,
        title=title,
        description=description,
        entities=(),
    )
    return infer_microtopic_identity_v7(document) is not None


def _completed_ids(path: Path, *, model: str, dimensions: int) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("model") != model or row.get("dimensions") != dimensions:
                raise ValueError(
                    f"existing embedding row {line_number} uses a different model or dimension"
                )
            completed.add(str(row["video_id"]))
    return completed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--max-videos", type=int)
    args = parser.parse_args()

    if not 1 <= args.batch_size <= 2_048:
        raise ValueError("batch size must be between 1 and 2048")
    provider = OpenAIEmbeddingProvider(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=args.model,
        dimensions=args.dimensions,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    completed = _completed_ids(args.output, model=args.model, dimensions=args.dimensions)
    videos = [
        video
        for video in load_structural_cohort(args.input)
        if _candidate(video.title, video.description, video.video_id)
        and video.video_id not in completed
    ]
    if args.max_videos is not None:
        videos = videos[: args.max_videos]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_tokens = 0
    written = 0
    with args.output.open("a", encoding="utf-8") as destination:
        for offset in range(0, len(videos), args.batch_size):
            batch = videos[offset : offset + args.batch_size]
            texts = [_embedding_text(video.title, video.description) for video in batch]
            result = provider.embed(texts)
            total_tokens += result.input_tokens
            for video, text, embedding in zip(batch, texts, result.embeddings, strict=True):
                row: dict[str, Any] = {
                    "dataset_version": EMBEDDING_DATASET_VERSION,
                    "video_id": video.video_id,
                    "source_hash": sha256(text.encode()).hexdigest(),
                    "model": result.model,
                    "dimensions": args.dimensions,
                    "embedding_base64": embedding.value,
                }
                destination.write(json.dumps(row, sort_keys=True) + "\n")
                written += 1
            destination.flush()
            print(
                json.dumps(
                    {
                        "embedded_this_run": written,
                        "remaining_this_run": len(videos) - written,
                        "input_tokens": total_tokens,
                    }
                ),
                flush=True,
            )

    metadata = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "dataset_version": EMBEDDING_DATASET_VERSION,
        "cohort_sha256": _hash(args.input),
        "embedding_file_sha256": _hash(args.output),
        "model": args.model,
        "dimensions": args.dimensions,
        "previously_completed": len(completed),
        "embedded_this_run": written,
        "input_tokens_this_run": total_tokens,
    }
    args.metadata_output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
