from packages.clustering import (
    MicrotopicDocument,
    cluster_microtopics_v7,
    infer_microtopic_identity_v7,
    normalize_format_neutral_title,
)


def _document(identifier: str, title: str, description: str = "") -> MicrotopicDocument:
    return MicrotopicDocument(
        id=identifier,
        title=title,
        description=description,
        entities=(),
    )


def test_v7_removes_format_markers_without_removing_subject() -> None:
    assert normalize_format_neutral_title("TensorFlow Tutorial for Beginners") == "TensorFlow"
    assert normalize_format_neutral_title("GPT-4 Developer Livestream") == "GPT-4 Developer"


def test_v7_gives_same_key_to_same_subject_context_across_formats() -> None:
    clusters = cluster_microtopics_v7(
        [
            _document("one", "TensorFlow neural network tutorial"),
            _document("two", "TensorFlow neural network explained"),
            _document("three", "TensorFlow neural network lecture"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].primary_entity == "TensorFlow"
    assert clusters[0].facet == "market_activity"
    assert len(clusters[0].document_ids) == 3


def test_v7_repairs_gpt4_livestream_identity_defect() -> None:
    clusters = cluster_microtopics_v7(
        [
            _document("one", "GPT-4 Developer Livestream"),
            _document("two", "GPT-4 Developer"),
        ]
    )

    assert len(clusters) == 1
    assert len(clusters[0].document_ids) == 2


def test_v7_keeps_material_product_versions_separate() -> None:
    clusters = cluster_microtopics_v7(
        [
            _document("one", "TensorFlow 1.0 released"),
            _document("two", "TensorFlow 2.0 released"),
        ]
    )

    assert {cluster.primary_entity for cluster in clusters} == {
        "TensorFlow 1",
        "TensorFlow 2",
    }


def test_v7_merges_equivalent_integer_and_dot_zero_versions() -> None:
    clusters = cluster_microtopics_v7(
        [
            _document("one", "TensorFlow 2 released"),
            _document("two", "TensorFlow 2.0 release announcement"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].primary_entity == "TensorFlow 2"


def test_v7_prefers_named_model_over_parent_domain() -> None:
    cluster = cluster_microtopics_v7(
        [_document("bert", "BERT research paper for natural language processing")]
    )[0]

    assert cluster.primary_entity == "BERT"


def test_v7_prefers_specific_ai_domain_over_generic_ai_anchor() -> None:
    identities = [
        infer_microtopic_identity_v7(_document("ethics", "AI ethics and bias risk")),
        infer_microtopic_identity_v7(_document("robotics", "AI robotics capability")),
    ]

    assert [identity.primary_entity for identity in identities if identity] == [
        "AI ethics",
        "AI robotics",
    ]


def test_v7_keeps_substantive_contexts_separate() -> None:
    clusters = cluster_microtopics_v7(
        [
            _document("release", "TensorFlow new version released"),
            _document("benchmark", "TensorFlow vs PyTorch performance benchmark"),
            _document("ethics", "TensorFlow face recognition privacy risk"),
        ]
    )

    assert {cluster.facet for cluster in clusters} == {
        "benchmark",
        "release_wave",
        "safety_ethics",
    }


def test_v7_supports_legacy_ai_subjects() -> None:
    titles = (
        "AlphaGo breakthrough beats world champion",
        "BERT research paper for natural language processing",
        "Generative Adversarial Networks explained",
        "DeepMind reinforcement learning capability",
        "Keras neural network tutorial",
    )

    identities = [
        infer_microtopic_identity_v7(_document(str(index), title))
        for index, title in enumerate(titles)
    ]

    assert all(identity is not None for identity in identities)


def test_v7_hides_generic_ai_market_activity() -> None:
    cluster = cluster_microtopics_v7([_document("generic", "Artificial Intelligence")])[0]

    assert cluster.visible is False
    assert "generic_subject_not_a_microtrend" in cluster.reason_codes


def test_v7_rejects_historical_gemini_astrology_collision() -> None:
    assert infer_microtopic_identity_v7(_document("astrology", "Gemini 2016 horoscope")) is None


def test_v7_rejects_gan_song_and_cube_collisions() -> None:
    assert infer_microtopic_identity_v7(_document("song", "TOMAY GAN SHONABO")) is None
    assert infer_microtopic_identity_v7(_document("cube", "GAN Air SM cube review")) is None
    assert (
        infer_microtopic_identity_v7(
            _document("ml", "Training a GAN neural network for image generation")
        )
        is not None
    )


def test_v7_rejects_keras_common_word_collision() -> None:
    assert infer_microtopic_identity_v7(_document("hard", "Dia bekerja keras setiap hari")) is None
    assert (
        infer_microtopic_identity_v7(_document("ml", "Training a Keras neural network")) is not None
    )


def test_v7_does_not_parse_arbitrary_adjacent_number_as_product_version() -> None:
    identity = infer_microtopic_identity_v7(_document("episode", "DeepMind 12 research update"))

    assert identity is not None
    assert identity.primary_entity == "DeepMind"


def test_v7_rejects_deepmind_synthesizer_collision() -> None:
    assert infer_microtopic_identity_v7(_document("synth", "Behringer DeepMind 12 demo")) is None
    assert (
        infer_microtopic_identity_v7(_document("lab", "Google DeepMind research update"))
        is not None
    )


def test_v7_rejects_neuro_linguistic_programming_nlp_collision() -> None:
    assert infer_microtopic_identity_v7(_document("hypnosis", "Hypnosis vs NLP showdown")) is None
    assert (
        infer_microtopic_identity_v7(
            _document("language", "NLP transformer model for language classification")
        )
        is not None
    )
