"""EarlySignal v2 core.

Pure, deterministic, I/O-free. The core never reads a clock, a database or the
network: the caller supplies the checkpoint, so a production run and a
historical replay execute the same code. See `docs/ARCHITECTURE_V2_RU.md`.
"""

from es_core.pipeline import PIPELINE_VERSION, PipelinePolicy, build_candidates
from es_core.ranking import MODEL_VERSION, AdoptionRanker, TrainingExample
from es_core.types import (
    Anchor,
    Candidate,
    Cluster,
    EvidenceVerdict,
    PanelMember,
    ScoredCandidate,
    TopicIdentity,
    Video,
)

__all__ = [
    "MODEL_VERSION",
    "PIPELINE_VERSION",
    "AdoptionRanker",
    "Anchor",
    "Candidate",
    "Cluster",
    "EvidenceVerdict",
    "PanelMember",
    "PipelinePolicy",
    "ScoredCandidate",
    "TopicIdentity",
    "TrainingExample",
    "Video",
    "build_candidates",
]
