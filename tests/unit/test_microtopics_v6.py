from packages.clustering import (
    MicrotopicDocument,
    cluster_microtopics_v6,
    infer_microtopic_identity_v6,
    normalize_entities,
)


def _document(identifier: str, title: str, description: str = "") -> MicrotopicDocument:
    return MicrotopicDocument(
        id=identifier,
        title=title,
        description=description,
        entities=tuple(normalize_entities(title, description)),
    )


def test_v6_maps_historical_ai_events_that_v5_dropped() -> None:
    titles = (
        "Did Google’s A.I. Just Become Sentient? Two Employees Think So.",
        "Google Panics Over ChatGPT [The AI Wars Have Begun]",
        "ChatGPT Has A Serious Problem",
        "Introducing Microsoft 365 Copilot | Your Copilot for Work",
        "OpenAI DevDay, Opening Keynote",
        "The Entire OpenAI Chaos Explained",
        "Nvidia 2024 AI Event: Everything Revealed in 16 Minutes",
        "The Race For AI Robots Just Got Real (OpenAI, NVIDIA and more)",
    )

    identities = [
        infer_microtopic_identity_v6(_document(str(index), title))
        for index, title in enumerate(titles)
    ]

    assert all(identity is not None for identity in identities)


def test_v6_merges_same_event_across_video_formats() -> None:
    clusters = cluster_microtopics_v6(
        [
            _document("one", "GPT-4 Developer Livestream"),
            _document("two", "GPT-4 launch explained: the new model capability"),
            _document("three", "Introducing GPT-4 for developers"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].visible is True
    assert len(clusters[0].document_ids) == 3
    assert clusters[0].label == "GPT-4 product and capability release"
    assert "livestream" not in clusters[0].label.lower()
    assert len(clusters[0].format_distribution) >= 1


def test_v6_merges_google_chatgpt_competitive_wave() -> None:
    clusters = cluster_microtopics_v6(
        [
            _document("one", "Google Panics Over ChatGPT [The AI Wars Have Begun]"),
            _document("two", "Google Embarrass Themselves (A.I. War Is Heating Up)"),
        ]
    )

    visible = [cluster for cluster in clusters if cluster.visible]
    assert len(visible) == 1
    assert visible[0].label == "Google–ChatGPT competitive response"


def test_v6_keeps_release_and_risk_as_different_trends() -> None:
    clusters = cluster_microtopics_v6(
        [
            _document("release", "OpenAI DevDay, Opening Keynote"),
            _document("risk", "OpenAI has a serious safety problem"),
        ]
    )

    assert len(clusters) == 2
    assert {cluster.facet for cluster in clusters} == {"release_wave", "risk_debate"}


def test_v6_rejects_unnamed_generic_release_from_visibility() -> None:
    cluster = cluster_microtopics_v6(
        [_document("generic", "A New AI Model Release Changed Everything")]
    )[0]

    assert cluster.visible is False
    assert "unnamed_release_without_product_anchor" in cluster.reason_codes
