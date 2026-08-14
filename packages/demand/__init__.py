from packages.demand.classifier import (
    CLASSIFIER_VERSION,
    COMMENT_EMBEDDING_VERSION,
    CommentAnalysis,
    classify_comment,
    taxonomy_label,
)
from packages.demand.relevance import (
    RELEVANCE_EMBEDDING_VERSION,
    RELEVANCE_MODEL_VERSION,
    RELEVANCE_THRESHOLD,
    CommentTopicRelevanceInput,
    CommentTopicRelevanceResult,
    classify_comment_topic_relevance,
    normalized_comment_fingerprint,
)

__all__ = [
    "CLASSIFIER_VERSION",
    "COMMENT_EMBEDDING_VERSION",
    "CommentAnalysis",
    "classify_comment",
    "taxonomy_label",
    "RELEVANCE_EMBEDDING_VERSION",
    "RELEVANCE_MODEL_VERSION",
    "RELEVANCE_THRESHOLD",
    "CommentTopicRelevanceInput",
    "CommentTopicRelevanceResult",
    "classify_comment_topic_relevance",
    "normalized_comment_fingerprint",
]
