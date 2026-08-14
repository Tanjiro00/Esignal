from packages.clustering.evidence_quality import EvidenceReleasePolicy
from scripts.audit_semantic_release_queue import _evidence_payload


def test_shadow_queue_preserves_independent_channel_and_family_metadata() -> None:
    candidate = {
        "evidence": [
            {
                "video_id": "video-a",
                "channel_id": "channel-a",
                "title": "Claude Code memory tutorial",
                "published_at": "2026-08-01T00:00:00+00:00",
            },
            {
                "video_id": "video-b",
                "channel_id": "channel-b",
                "title": "Persistent context in Claude Code explained",
                "published_at": "2026-08-02T00:00:00+00:00",
            },
        ]
    }

    evidence, metadata = _evidence_payload(candidate, EvidenceReleasePolicy())

    assert [item.ref for item in evidence] == ["video:video-a", "video:video-b"]
    assert {item["channel_id"] for item in metadata.values()} == {
        "channel-a",
        "channel-b",
    }
    assert len({item["title_family"] for item in metadata.values()}) == 2
