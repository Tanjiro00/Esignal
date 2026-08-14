from packages.transcripts import process_transcript


def test_processing_returns_bounded_extracts_and_timed_evidence() -> None:
    segments = tuple(
        (
            float(index * 8),
            float(index * 8 + 8),
            (
                f"Step {index} uses a local AI video model to build a practical "
                "workflow and compare cost versus the hosted alternative."
            ),
        )
        for index in range(18)
    )

    result = process_transcript(
        title="Local AI Video Models Compared",
        full_text=" ".join(segment[2] for segment in segments),
        segments=segments,
    )

    evidence = [segment for segment in result.segments if segment.is_evidence]
    assert 1 <= len(evidence) <= 5
    assert all(len(segment.text) <= 280 for segment in result.segments)
    assert all(segment.end_seconds >= segment.start_seconds for segment in result.segments)
    assert len(result.summary["text"]) <= 480
    assert result.summary["method"] == "extractive"
    assert result.content_format == "comparison"
    assert result.entities


def test_processing_handles_empty_transcript_without_fabrication() -> None:
    result = process_transcript(title="AI update", full_text="", segments=())

    assert result.summary == {"text": "", "method": "extractive"}
    assert result.key_claims == []
    assert result.segments == []
