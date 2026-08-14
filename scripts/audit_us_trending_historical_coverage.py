from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.backtest.external_timeseries import (
    EXTERNAL_REPLAY_VERSION,
    ExternalTimeseriesReplay,
    _looks_english,
    _matches_vertical,
)
from packages.backtest.trending_archive import (
    US_TRENDING_ARCHIVE_VERSION,
    load_us_trending_archive,
)

STRICT_AI_TECH_CATEGORIES = frozenset({"25", "26", "27", "28"})


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(path: Path) -> dict[str, Any]:
    videos = load_us_trending_archive(path)
    replay = ExternalTimeseriesReplay(
        videos,
        eligible_categories=STRICT_AI_TECH_CATEGORIES,
    )
    admitted = [
        video
        for video in videos
        if video.category in STRICT_AI_TECH_CATEGORIES
        and _looks_english(video.title)
        and _matches_vertical(video.title)
    ]
    rows: list[dict[str, Any]] = []
    for video in sorted(admitted, key=lambda item: (item.published_at, item.video_id)):
        topic_key = replay._topic_key_by_video.get(video.video_id)
        first_observed = video.snapshots[0].observed_at
        state = replay.states_at(first_observed).get(topic_key) if topic_key else None
        rows.append(
            {
                "video_id": video.video_id,
                "title": video.title,
                "published_at": video.published_at.isoformat(),
                "first_trending_at": first_observed.isoformat(),
                "topic_key": topic_key,
                "topic_visible": state is not None,
                "topic_actionable": state.actionable if state is not None else False,
                "topic_label": state.label if state is not None else None,
                "score": state.score if state is not None else None,
            }
        )
    mapped = sum(row["topic_key"] is not None for row in rows)
    visible = sum(bool(row["topic_visible"]) for row in rows)
    actionable = sum(bool(row["topic_actionable"]) for row in rows)
    checkpoints = sorted(
        {
            snapshot.observed_at
            for video in admitted
            if video.video_id in replay._topic_key_by_video
            for snapshot in video.snapshots
        }
    )
    checkpoint_states = [(checkpoint, replay.states_at(checkpoint)) for checkpoint in checkpoints]
    checkpoints_with_visible = sum(bool(states) for _, states in checkpoint_states)
    checkpoints_with_actionable = sum(
        any(state.actionable for state in states.values()) for _, states in checkpoint_states
    )
    ever_actionable_topics = {
        state.topic_key
        for _, states in checkpoint_states
        for state in states.values()
        if state.actionable
    }
    all_visible_states = [state for _, states in checkpoint_states for state in states.values()]
    return {
        "audit_version": "us-trending-historical-coverage-v2-v6-taxonomy",
        "replay_version": EXTERNAL_REPLAY_VERSION,
        "archive_version": US_TRENDING_ARCHIVE_VERSION,
        "dataset_sha256": _hash_file(path),
        "selection_boundary": (
            "US Trending contains videos only after they enter the trending chart. "
            "This audit tests taxonomy/actionability coverage at first trending observation; "
            "it is not a pre-trending precision estimate."
        ),
        "archive_video_count": len(videos),
        "archive_snapshot_count": sum(len(video.snapshots) for video in videos),
        "strict_ai_tech_title_count": len(rows),
        "mapped_topic_count": mapped,
        "visible_topic_count_at_first_trending": visible,
        "actionable_topic_count_at_first_trending": actionable,
        "mapping_recall_percent": round(mapped / len(rows) * 100, 1) if rows else 0,
        "visibility_recall_percent": round(visible / len(rows) * 100, 1) if rows else 0,
        "actionable_recall_percent": round(actionable / len(rows) * 100, 1) if rows else 0,
        "historical_wave_replay": {
            "checkpoint_count": len(checkpoints),
            "checkpoints_with_visible_topics": checkpoints_with_visible,
            "checkpoints_with_actionable_topics": checkpoints_with_actionable,
            "ever_actionable_topic_count": len(ever_actionable_topics),
            "max_visible_topics_at_checkpoint": max(
                (len(states) for _, states in checkpoint_states),
                default=0,
            ),
            "max_video_count_in_visible_topic": max(
                (state.video_count for state in all_visible_states),
                default=0,
            ),
            "max_distinct_channels_in_visible_topic": max(
                (state.distinct_channels for state in all_visible_states),
                default=0,
            ),
        },
        "videos": rows,
    }


def _markdown(payload: dict[str, Any]) -> str:
    replay = payload["historical_wave_replay"]
    coverage_passed = payload["mapping_recall_percent"] >= 90
    coverage_verdict = "PASS" if coverage_passed else "FAIL"
    rows = [
        "# EarlySignal US Trending v6 historical coverage and wave replay",
        "",
        f"**Taxonomy coverage: {coverage_verdict}. Predictive validation: NOT ESTABLISHED.**",
        "",
        f"- Archive videos: {payload['archive_video_count']}",
        f"- Daily snapshots: {payload['archive_snapshot_count']}",
        f"- Strict AI/tech titles that actually reached US Trending: "
        f"{payload['strict_ai_tech_title_count']}",
        f"- Titles mapped to any production topic identity: {payload['mapped_topic_count']} "
        f"({payload['mapping_recall_percent']}%)",
        f"- Visible at first Trending observation: "
        f"{payload['visible_topic_count_at_first_trending']} "
        f"({payload['visibility_recall_percent']}%)",
        f"- Actionable at first Trending observation: "
        f"{payload['actionable_topic_count_at_first_trending']} "
        f"({payload['actionable_recall_percent']}%)",
        "",
        "## Interpretation",
        "",
        "The v6 subject/event taxonomy fixes the admission failure seen in v5: clear AI/tech "
        "titles are now mapped without treating video format as trend identity. This establishes "
        "taxonomy coverage only; it does not establish predictive power.",
        "",
        "The fixed production evidence gate still emitted no actionable topic. The archive is "
        "sparse at the microtrend level and often contains only one publishing channel per "
        "subject/event identity. We did not weaken the three-channel corroboration rule to force "
        "a positive result.",
        "",
        "This is a negative/indeterminate replay result, not a complete pre-trending backtest. "
        "US Trending contains only videos after selection into the chart and omits the "
        "non-trending candidate universe, so unbiased precision, false-positive rate and lead "
        "time cannot be estimated from it.",
        "",
        "## Historical wave replay",
        "",
        f"- Observed checkpoints across admitted mapped videos: {replay['checkpoint_count']}",
        f"- Checkpoints with at least one visible topic: "
        f"{replay['checkpoints_with_visible_topics']}",
        f"- Checkpoints with at least one actionable topic: "
        f"{replay['checkpoints_with_actionable_topics']}",
        f"- Topic identities ever actionable: {replay['ever_actionable_topic_count']}",
        f"- Maximum visible topics at one checkpoint: {replay['max_visible_topics_at_checkpoint']}",
        f"- Maximum videos in one visible identity: {replay['max_video_count_in_visible_topic']}",
        f"- Maximum distinct channels in one visible identity: "
        f"{replay['max_distinct_channels_in_visible_topic']}",
        "",
        "## Audited videos",
        "",
        "| First trending | Title | Mapped | Visible | Actionable | Topic |",
        "|---|---|---|---|---|---|",
    ]
    for item in payload["videos"]:
        title = str(item["title"]).replace("|", "\\|")
        topic = str(item["topic_label"] or "").replace("|", "\\|")
        rows.append(
            f"| {str(item['first_trending_at'])[:10]} | {title} | "
            f"{'yes' if item['topic_key'] else 'no'} | "
            f"{'yes' if item['topic_visible'] else 'no'} | "
            f"{'yes' if item['topic_actionable'] else 'no'} | {topic} |"
        )
    rows.extend(
        [
            "",
            "## Reproducibility",
            "",
            f"- Dataset SHA-256: `{payload['dataset_sha256']}`",
            f"- Archive adapter: `{payload['archive_version']}`",
            f"- Replay core: `{payload['replay_version']}`",
            "- Source: https://www.kaggle.com/datasets/rsrishav/youtube-trending-video-dataset",
            "- License: CC0 (as declared by the dataset publisher)",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    payload = audit(args.dataset)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "strict_ai_tech_titles": payload["strict_ai_tech_title_count"],
                "mapped": payload["mapped_topic_count"],
                "actionable": payload["actionable_topic_count_at_first_trending"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
