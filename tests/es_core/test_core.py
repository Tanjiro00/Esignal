from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from es_core import features as feature_builder
from es_core.anchors import AnchorExtractor, AnchorPolicy, BackgroundCorpus
from es_core.clustering import ClusterPolicy, cluster_videos
from es_core.evidence import assess, copy_families, template_channels
from es_core.features import LeakageError, burst_state
from es_core.identity import TopicRegistry
from es_core.outcome import evaluate_adoption
from es_core.pipeline import PipelinePolicy, build_candidates, panel_at
from es_core.ranking import (
    AdoptionRanker,
    InsufficientTrainingData,
    TrainingExample,
    purged_splits,
)
from es_core.types import Cluster, PanelMember, Video

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def video(
    video_id: str,
    channel_id: str,
    title: str,
    *,
    days_ago: float = 1.0,
    discovered_days_ago: float | None = None,
) -> Video:
    published = NOW - timedelta(days=days_ago)
    discovered = NOW - timedelta(
        days=discovered_days_ago if discovered_days_ago is not None else days_ago
    )
    return Video(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        published_at=published,
        discovered_at=discovered,
    )


def background(count: int = 200) -> list[Video]:
    """A generic panel background: lots of tutorials, no specific subject."""

    generic = [
        "how to make an AI video for beginners",
        "best AI tools this week full guide",
        "AI workflow tutorial step by step",
        "make money with AI automation",
        "AI agent tutorial for beginners",
    ]
    return [
        video(
            f"bg{index}",
            f"chan{index % 40}",
            generic[index % len(generic)],
            days_ago=30 + index % 300,
        )
        for index in range(count)
    ]


def unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def embedding_for(seed: int, topic: int, dimensions: int = 32) -> list[float]:
    """Deterministic vector: a strong topic direction plus small per-video noise."""

    generator = random.Random(seed)
    base = random.Random(1000 + topic)
    base_vector = [base.gauss(0, 1) for _ in range(dimensions)]
    noise = [generator.gauss(0, 0.12) for _ in range(dimensions)]
    return unit([b + n for b, n in zip(base_vector, noise, strict=True)])


# --------------------------------------------------------------------------- anchors


def test_new_product_term_outranks_generic_term_without_any_word_list() -> None:
    """A never-before-seen product name must anchor a topic on day one.

    This is the property v1 could not have: its taxonomy was a hardcoded list of
    25 brands, so an unknown product was invisible by construction.
    """

    corpus_videos = background()
    cluster_members = [
        video("n1", "c1", "Seedance 2 cinematic workflow tested", days_ago=2),
        video("n2", "c2", "I tried Seedance 2 for product shots", days_ago=3),
        video("n3", "c3", "Seedance 2 versus the old pipeline", days_ago=1),
    ]
    corpus = BackgroundCorpus.build([*corpus_videos, *cluster_members], as_of=NOW)
    extractor = AnchorExtractor(corpus, policy=AnchorPolicy(minimum_channel_support=2))

    anchors = extractor.extract(cluster_members)
    terms = [anchor.term for anchor in anchors]

    assert any("seedance" in term for term in terms), terms
    assert extractor.anchored(anchors)
    # Generic panel vocabulary must not anchor anything.
    assert not any(term in {"ai", "video", "tutorial", "workflow"} for term in terms)


def test_broad_tutorial_cluster_has_no_anchor() -> None:
    corpus_videos = background()
    members = [
        video("t1", "c1", "how to make an AI video for beginners", days_ago=2),
        video("t2", "c2", "AI workflow tutorial step by step", days_ago=3),
        video("t3", "c3", "best AI tools this week full guide", days_ago=1),
    ]
    corpus = BackgroundCorpus.build([*corpus_videos, *members], as_of=NOW)
    extractor = AnchorExtractor(corpus)

    assert not extractor.anchored(extractor.extract(members))


def test_background_corpus_ignores_unobservable_videos() -> None:
    late = video("late", "c9", "Seedance 2 breakdown", days_ago=1, discovered_days_ago=-5)
    corpus = BackgroundCorpus.build([*background(), late], as_of=NOW)

    assert corpus.first_seen_at("seedance") is None


# -------------------------------------------------------------------------- evidence


def test_copy_farm_is_rejected_and_genuine_spread_is_accepted() -> None:
    corpus = BackgroundCorpus.build(background(), as_of=NOW)
    title = "Higgsfield AI is DEAD use HeyGen instead"
    copies = [video(f"x{index}", f"c{index}", title, days_ago=index + 1) for index in range(5)]

    verdict = assess(copies, corpus)

    assert verdict.status == "rejected"
    assert "single_repeated_angle" in verdict.reasons
    assert len(verdict.family_head_ids) == 1

    genuine = [
        video("g1", "c1", "Seedance 2 cinematic camera control breakdown", days_ago=2),
        video("g2", "c2", "why Seedance 2 changes my storyboard process", days_ago=3),
        video("g3", "c3", "Seedance 2 pricing and limits after a week", days_ago=1),
    ]
    assert assess(genuine, corpus).status == "accepted"


def test_copy_families_keep_the_earliest_upload_as_head() -> None:
    corpus = BackgroundCorpus.build(background(), as_of=NOW)
    title = "Seedance 2 cinematic workflow full breakdown"
    videos = [
        video("late", "c2", title, days_ago=1),
        video("early", "c1", title, days_ago=6),
    ]

    families = copy_families(videos, corpus)

    assert len(families) == 1
    assert families[0][0].video_id == "early"


def test_template_channels_are_detected_from_behaviour() -> None:
    corpus = BackgroundCorpus.build(background(), as_of=NOW)
    farm = [
        video(f"f{index}", "farm", "Seedance 2 cinematic workflow breakdown", days_ago=index + 1)
        for index in range(6)
    ]
    varied = [
        video("v1", "real", "Seedance 2 camera control test", days_ago=2),
        video("v2", "real", "my Blender to Seedance pipeline", days_ago=4),
        video("v3", "real", "why I stopped paying for stock footage", days_ago=6),
    ]

    flagged = template_channels([*farm, *varied], corpus)

    assert flagged == frozenset({"farm"})


# -------------------------------------------------------------------------- features


def test_feature_builder_refuses_future_evidence() -> None:
    corpus_cluster = Cluster(
        members=(video("f1", "c1", "Seedance 2 test", days_ago=-3),),
        centroid=(1.0, 0.0),
        exemplars=((1.0, 0.0),),
        mean_similarity=0.9,
        minimum_similarity=0.9,
    )
    verdict = assess([], BackgroundCorpus.build([], as_of=NOW))

    with pytest.raises(LeakageError):
        feature_builder.build(
            corpus_cluster,
            as_of=NOW,
            history=(),
            anchors=(),
            evidence=verdict,
            topic_age_days=1.0,
        )


def test_burst_state_separates_a_burst_from_a_flat_stream() -> None:
    flat = [NOW - timedelta(days=day) for day in range(0, 28, 2)]
    bursty = [NOW - timedelta(days=day) for day in range(0, 3) for _ in range(6)]

    assert burst_state(flat, as_of=NOW) < burst_state(bursty, as_of=NOW)


# -------------------------------------------------------------------------- identity


def test_topic_identity_survives_new_members_across_checkpoints() -> None:
    registry = TopicRegistry()
    first = Cluster(
        members=(video("a", "c1", "Seedance 2 test", days_ago=3),),
        centroid=(1.0, 0.0, 0.0),
        exemplars=((1.0, 0.0, 0.0),),
        mean_similarity=0.95,
        minimum_similarity=0.95,
    )
    topic = registry.assign(first, (), as_of=NOW - timedelta(days=7))

    second = Cluster(
        members=(
            video("a", "c1", "Seedance 2 test", days_ago=10),
            video("b", "c2", "Seedance 2 review", days_ago=1),
        ),
        centroid=(0.97, 0.24, 0.0),
        exemplars=((0.97, 0.24, 0.0),),
        mean_similarity=0.93,
        minimum_similarity=0.9,
    )
    continued = registry.assign(second, (), as_of=NOW)

    assert continued.topic_id == topic.topic_id
    assert continued.first_seen_at == topic.first_seen_at
    assert registry.age_days(topic.topic_id, NOW) == pytest.approx(7.0)
    assert [event.kind for event in registry.lineage] == ["created", "continue"]


def test_unrelated_cluster_creates_a_separate_topic() -> None:
    registry = TopicRegistry()
    left = Cluster(
        members=(video("a", "c1", "Seedance 2", days_ago=2),),
        centroid=(1.0, 0.0),
        exemplars=((1.0, 0.0),),
        mean_similarity=0.9,
        minimum_similarity=0.9,
    )
    right = Cluster(
        members=(video("b", "c2", "Kling 3 motion", days_ago=2),),
        centroid=(0.0, 1.0),
        exemplars=((0.0, 1.0),),
        mean_similarity=0.9,
        minimum_similarity=0.9,
    )

    first = registry.assign(left, (), as_of=NOW)
    second = registry.assign(right, (), as_of=NOW)

    assert first.topic_id != second.topic_id


# -------------------------------------------------------------------------- clustering


def test_clustering_separates_two_synthetic_topics() -> None:
    videos = []
    embeddings = {}
    for index in range(4):
        item = video(f"a{index}", f"ca{index}", f"Seedance 2 angle {index}", days_ago=index + 1)
        videos.append(item)
        embeddings[item.video_id] = embedding_for(index, topic=1)
    for index in range(4):
        item = video(f"b{index}", f"cb{index}", f"Kling 3 motion take {index}", days_ago=index + 1)
        videos.append(item)
        embeddings[item.video_id] = embedding_for(100 + index, topic=2)

    clusters = cluster_videos(videos, embeddings, policy=ClusterPolicy(minimum_channels=2))

    assert len(clusters) == 2
    for cluster in clusters:
        prefixes = {member.video_id[0] for member in cluster.members}
        assert len(prefixes) == 1


def test_videos_without_embeddings_are_skipped_not_guessed() -> None:
    items = [
        video(f"a{index}", f"c{index}", "Seedance 2", days_ago=index + 1) for index in range(4)
    ]
    embeddings = {
        item.video_id: embedding_for(index, topic=1) for index, item in enumerate(items[:2])
    }

    clusters = cluster_videos(items, embeddings)

    assert all(len(cluster.members) <= 2 for cluster in clusters)


# --------------------------------------------------------------------------- outcome


def test_adoption_requires_new_channels_inside_the_frozen_panel() -> None:
    corpus = BackgroundCorpus.build(background(), as_of=NOW)
    prior = frozenset({"c1"})
    future = [
        Video(
            "n1",
            "c2",
            "Seedance 2 camera control",
            NOW + timedelta(days=3),
            NOW + timedelta(days=3),
        ),
        Video(
            "n2",
            "c3",
            "Seedance 2 vs Kling for ads",
            NOW + timedelta(days=5),
            NOW + timedelta(days=5),
        ),
        Video(
            "n3",
            "c4",
            "Seedance 2 pricing breakdown",
            NOW + timedelta(days=9),
            NOW + timedelta(days=9),
        ),
        Video(
            "n4",
            "c5",
            "using Seedance 2 in a real client project",
            NOW + timedelta(days=12),
            NOW + timedelta(days=12),
        ),
    ]

    fired = evaluate_adoption(
        as_of=NOW,
        prior_channel_ids=prior,
        previous_28d_video_count=2,
        future_videos=future,
        corpus=corpus,
    )
    assert fired.fired
    assert fired.lead_days is not None and fired.lead_days > 0

    # Channels outside the panel frozen at t0 cannot create an outcome.
    outside = evaluate_adoption(
        as_of=NOW,
        prior_channel_ids=prior,
        previous_28d_video_count=2,
        future_videos=future,
        corpus=corpus,
        panel_at_t0=frozenset({"c1", "c2"}),
    )
    assert not outside.fired


def test_copied_future_titles_do_not_create_adoption() -> None:
    corpus = BackgroundCorpus.build(background(), as_of=NOW)
    title = "Seedance 2 cinematic workflow full breakdown"
    future = [
        Video(
            f"n{index}",
            f"c{index}",
            title,
            NOW + timedelta(days=index + 1),
            NOW + timedelta(days=index + 1),
        )
        for index in range(8)
    ]

    outcome = evaluate_adoption(
        as_of=NOW,
        prior_channel_ids=frozenset({"c0"}),
        previous_28d_video_count=2,
        future_videos=future,
        corpus=corpus,
    )

    assert outcome.future_family_count == 1
    assert not outcome.fired


# --------------------------------------------------------------------------- ranking


def test_purged_splits_embargo_the_outcome_horizon() -> None:
    examples = [
        TrainingExample(NOW - timedelta(days=200 - index * 2), {"x": float(index)}, index % 3 == 0)
        for index in range(100)
    ]

    splits = purged_splits(examples, folds=4, horizon_days=42)

    assert splits
    for train, validation in splits:
        start = min(examples[index].as_of for index in validation)
        assert all(examples[index].as_of + timedelta(days=42) <= start for index in train)


def test_ranker_refuses_to_fit_on_thin_data() -> None:
    ranker = AdoptionRanker(("x",))
    with pytest.raises(InsufficientTrainingData):
        ranker.fit([TrainingExample(NOW, {"x": 1.0}, True)])


def test_ranker_learns_a_separable_signal_and_abstains_on_weak_evidence() -> None:
    generator = random.Random(7)
    training: list[TrainingExample] = []
    for index in range(200):
        label = index % 2 == 0
        value = generator.gauss(2.0 if label else -2.0, 0.5)
        training.append(
            TrainingExample(NOW - timedelta(days=200 - index), {"signal": value}, label)
        )

    ranker = AdoptionRanker(("signal",)).fit(training)
    scores = ranker.rank_scores([{"signal": 2.0}, {"signal": -2.0}])

    assert scores[0] > scores[1]
    assert ranker.calibrate(training[-100:])
    probabilities = ranker.probabilities([{"signal": 2.0}, {"signal": -2.0}])
    assert probabilities is not None and probabilities[0] > probabilities[1]


# -------------------------------------------------------------------------- pipeline


def test_pipeline_builds_anchored_candidates_and_respects_the_frozen_panel() -> None:
    corpus_videos = background()
    embeddings = {
        item.video_id: embedding_for(index, topic=index % 7)
        for index, item in enumerate(corpus_videos)
    }

    members = [
        video("s1", "c1", "Seedance 2 cinematic camera control breakdown", days_ago=2),
        video("s2", "c2", "why Seedance 2 changed my storyboard process", days_ago=4),
        video("s3", "c3", "Seedance 2 pricing and limits after one week", days_ago=6),
    ]
    for index, item in enumerate(members):
        embeddings[item.video_id] = embedding_for(500 + index, topic=42)

    panel = [PanelMember(f"c{index}", NOW - timedelta(days=365)) for index in range(1, 4)]
    panel.extend(PanelMember(f"chan{index}", NOW - timedelta(days=365)) for index in range(40))

    candidates = build_candidates(
        [*corpus_videos, *members],
        embeddings,
        as_of=NOW,
        registry=TopicRegistry(),
        panel=panel,
        policy=PipelinePolicy(clustering=ClusterPolicy(minimum_channels=2)),
    )

    seedance = [
        candidate
        for candidate in candidates
        if any("seedance" in anchor.term for anchor in candidate.anchors)
    ]
    assert seedance, [candidate.label for candidate in candidates]
    assert seedance[0].publishable
    assert seedance[0].features["log_active_supply"] > 0

    # A channel that joins the panel later must not be visible at this checkpoint.
    assert panel_at([PanelMember("late", NOW + timedelta(days=1))], NOW) == frozenset()


def test_pipeline_is_deterministic() -> None:
    corpus_videos = background(60)
    embeddings = {
        item.video_id: embedding_for(index, topic=index % 5)
        for index, item in enumerate(corpus_videos)
    }

    first = build_candidates(corpus_videos, embeddings, as_of=NOW, registry=TopicRegistry())
    second = build_candidates(corpus_videos, embeddings, as_of=NOW, registry=TopicRegistry())

    assert [candidate.features for candidate in first] == [
        candidate.features for candidate in second
    ]
