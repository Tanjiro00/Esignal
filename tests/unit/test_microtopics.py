from packages.clustering import MicrotopicDocument, cluster_microtopics


def _document(identifier: str, title: str, entities: tuple[str, ...]) -> MicrotopicDocument:
    return MicrotopicDocument(
        id=identifier,
        title=title,
        description="",
        entities=entities,
    )


def test_microtopics_split_broad_domains_by_concrete_use_case() -> None:
    clusters = cluster_microtopics(
        [
            _document(
                "video-1",
                "How to Build Your First AI Agent as a Beginner",
                ("AI agents",),
            ),
            _document(
                "video-2",
                "From Zero to Advanced AI Agents With No Coding",
                ("AI agents",),
            ),
            _document(
                "video-3",
                "AI Agents Full Course for Beginners",
                ("AI agents",),
            ),
            _document(
                "video-4",
                "An AI Agent Cleared My Worst Recurring Task",
                ("AI agents",),
            ),
        ]
    )

    assert len(clusters) == 2
    beginner = next(cluster for cluster in clusters if cluster.facet == "beginner_no_code")
    applied = next(cluster for cluster in clusters if cluster.facet == "applied_workflows")
    assert beginner.label.startswith("Beginner and no-code AI agents")
    assert len(beginner.document_ids) == 3
    assert applied.document_ids == ("video-4",)


def test_microtopic_identity_is_stable_across_document_order() -> None:
    documents = [
        _document(
            "video-1",
            "Make Free and Unlimited AI Videos on Your PC",
            ("AI video generation",),
        ),
        _document(
            "video-2",
            "Free Local AI Video Generation Without a Paywall",
            ("AI video generation",),
        ),
    ]

    first = cluster_microtopics(documents)[0]
    second = cluster_microtopics(list(reversed(documents)))[0]

    assert first.key == second.key
    assert first.label == second.label


def test_release_topics_require_and_split_by_named_product() -> None:
    clusters = cluster_microtopics(
        [
            _document(
                "video-1",
                "New Claude Code Release Changes Agentic Coding",
                ("Claude Code", "Coding agents"),
            ),
            _document(
                "video-2",
                "Claude Code Release Is Here",
                ("Claude Code", "Coding agents"),
            ),
            _document(
                "video-3",
                "New Gemini Release Changes Agentic Coding",
                ("Gemini", "Coding agents"),
            ),
            _document(
                "video-4",
                "A New Model Release With No Product Name",
                ("AI models",),
            ),
        ]
    )

    assert {cluster.label for cluster in clusters} == {
        "New Claude Code release",
        "New Gemini release",
    }
    assert all(":" not in cluster.label for cluster in clusters)
