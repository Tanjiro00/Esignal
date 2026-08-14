"""Micro-topic clustering over real sentence embeddings.

Settings that were validated in the v1 replay are kept: HDBSCAN with
``cluster_selection_method="leaf"`` (leaf selection yields narrow micro-topics
rather than broad domains) and the cohesion floors of 0.72 mean / 0.62 minimum
member similarity.

One addition: the niche centroid is subtracted before clustering. Every video in
a single-niche panel is somewhat similar to every other, and that shared
component dominates the distance matrix. Removing it sharpens the differences
that actually separate micro-topics. The strength ``lambda`` is a train-period
hyper-parameter and never tuned on an evaluation window.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from sklearn.cluster import HDBSCAN

from es_core.types import Cluster, Video, sorted_videos

FloatMatrix = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class ClusterPolicy:
    minimum_cluster_size: int = 2
    minimum_samples: int = 2
    cluster_selection_method: str = "leaf"
    minimum_members: int = 2
    maximum_members: int = 60
    minimum_channels: int = 2
    minimum_mean_similarity: float = 0.72
    minimum_member_similarity: float = 0.62
    niche_centroid_strength: float = 0.30
    exemplar_count: int = 5


def normalize(vector: npt.ArrayLike) -> FloatMatrix:
    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def remove_niche_component(matrix: FloatMatrix, *, strength: float) -> FloatMatrix:
    """Subtract the shared direction of the panel and renormalize."""

    if strength <= 0.0 or matrix.shape[0] < 2:
        return matrix
    niche = normalize(matrix.mean(axis=0))
    adjusted = matrix - strength * np.outer(matrix @ niche, niche)
    norms = np.linalg.norm(adjusted, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (adjusted / norms).astype(np.float32)


def cluster_videos(
    videos: Sequence[Video],
    embeddings: Mapping[str, Sequence[float]],
    *,
    policy: ClusterPolicy | None = None,
) -> tuple[Cluster, ...]:
    """Group uploads into cohesive micro-topics.

    Videos without an embedding are skipped rather than guessed at; a missing
    vector is an ingestion problem and must not become a silent clustering
    decision.
    """

    active = policy or ClusterPolicy()
    usable = tuple(video for video in sorted_videos(videos) if video.video_id in embeddings)
    if len(usable) < active.minimum_cluster_size:
        return ()

    raw = np.stack([normalize(embeddings[video.video_id]) for video in usable]).astype(np.float32)
    matrix = remove_niche_component(raw, strength=active.niche_centroid_strength)
    labels = HDBSCAN(
        min_cluster_size=active.minimum_cluster_size,
        min_samples=active.minimum_samples,
        metric="euclidean",
        cluster_selection_method=active.cluster_selection_method,
        copy=True,
    ).fit_predict(matrix)

    clusters: list[Cluster] = []
    for label in sorted({int(value) for value in labels if value >= 0}):
        indexes = np.flatnonzero(labels == label)
        members = tuple(usable[int(index)] for index in indexes)
        if not active.minimum_members <= len(members) <= active.maximum_members:
            continue
        if len({video.channel_id for video in members}) < active.minimum_channels:
            continue
        member_matrix = raw[indexes]
        centroid = normalize(member_matrix.mean(axis=0))
        similarities = member_matrix @ centroid
        mean_similarity = float(similarities.mean())
        minimum_similarity = float(similarities.min())
        if (
            mean_similarity < active.minimum_mean_similarity
            or minimum_similarity < active.minimum_member_similarity
        ):
            continue
        order = np.argsort(-similarities)[: min(active.exemplar_count, len(members))]
        clusters.append(
            Cluster(
                members=members,
                centroid=tuple(float(value) for value in centroid),
                exemplars=tuple(
                    tuple(float(value) for value in member_matrix[int(index)]) for index in order
                ),
                mean_similarity=round(mean_similarity, 6),
                minimum_similarity=round(minimum_similarity, 6),
            )
        )
    return tuple(clusters)


def assign_to_clusters(
    videos: Sequence[Video],
    embeddings: Mapping[str, Sequence[float]],
    clusters: Sequence[Cluster],
    *,
    centroid_similarity: float = 0.74,
    exemplar_similarity: float = 0.78,
) -> dict[int, tuple[Video, ...]]:
    """Assign later uploads to at most one existing cluster.

    Used by the outcome evaluator: future videos are credited to the single
    nearest topic that clears both radii, never to several at once.
    """

    assignments: dict[int, list[Video]] = {index: [] for index in range(len(clusters))}
    if not clusters:
        return {}
    usable = tuple(video for video in sorted_videos(videos) if video.video_id in embeddings)
    if not usable:
        return {index: () for index in range(len(clusters))}
    matrix = np.stack([normalize(embeddings[video.video_id]) for video in usable]).astype(
        np.float32
    )
    scores = np.full((len(usable), len(clusters)), -np.inf, dtype=np.float32)
    for index, cluster in enumerate(clusters):
        centroid = np.asarray(cluster.centroid, dtype=np.float32)
        exemplars = np.asarray(cluster.exemplars, dtype=np.float32)
        to_centroid = matrix @ centroid
        to_exemplar = (matrix @ exemplars.T).max(axis=1)
        valid = (to_centroid >= centroid_similarity) & (to_exemplar >= exemplar_similarity)
        scores[:, index] = np.where(valid, (to_centroid + to_exemplar) / 2, -np.inf)
    nearest = scores.argmax(axis=1)
    best = scores.max(axis=1)
    for position in np.flatnonzero(np.isfinite(best)).tolist():
        assignments[int(nearest[position])].append(usable[position])
    return {index: tuple(values) for index, values in assignments.items()}


__all__ = [
    "ClusterPolicy",
    "FloatMatrix",
    "assign_to_clusters",
    "cluster_videos",
    "normalize",
    "remove_niche_component",
]
