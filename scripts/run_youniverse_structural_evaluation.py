from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class CandidateVariant:
    name: str
    minimum_channels: int
    recent_window_days: int
    maximum_active_videos: int
    episode_cooldown_days: int


PRIMARY_VARIANT = CandidateVariant("primary", 3, 7, 25, 42)
FALLBACK_LADDER = (
    CandidateVariant("fallback_1", 2, 7, 25, 42),
    CandidateVariant("fallback_2", 3, 14, 25, 42),
    CandidateVariant("fallback_3", 2, 14, 25, 42),
    CandidateVariant("fallback_4", 3, 14, 40, 42),
    CandidateVariant("fallback_5", 2, 14, 40, 42),
)
CANONICAL_TRAIN = "YOUNIVERSE_STRUCTURAL_TRAIN_2026-08-09"
CANONICAL_HOLDOUT = "YOUNIVERSE_STRUCTURAL_HOLDOUT_2026-08-09"
SELECTION_FILE = "YOUNIVERSE_STRUCTURAL_SELECTED_POLICY_2026-08-09.json"
ROBUSTNESS_PREFIX = "YOUNIVERSE_STRUCTURAL_HOLDOUT_ROBUSTNESS_2026-08-09"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_feasibility(payload: dict[str, Any]) -> dict[str, bool]:
    metrics = payload["metrics"]
    method = metrics["rankings"]["method"]
    episode_coverage = method["prediction_outcome_baseline_coverage_percent"]
    video_coverage = method["future_video_baseline_coverage_percent"]
    return {
        "at_least_50_candidate_episodes": metrics["candidate_topics"] >= 50,
        "at_least_50_method_predictions": method["predictions"] >= 50,
        "at_least_80_percent_prediction_episode_coverage": episode_coverage is not None
        and episode_coverage >= 80,
        "at_least_80_percent_future_video_coverage": video_coverage is not None
        and video_coverage >= 80,
    }


def is_train_feasible(payload: dict[str, Any]) -> bool:
    return all(train_feasibility(payload).values())


def select_train_variant(
    evaluated: list[tuple[CandidateVariant, dict[str, Any]]],
) -> CandidateVariant:
    for variant, payload in evaluated:
        if is_train_feasible(payload):
            return variant
    return PRIMARY_VARIANT


def robustness_variants(selected: CandidateVariant) -> tuple[CandidateVariant, ...]:
    candidates = (
        replace(selected, name="minimum_channels_5", minimum_channels=5),
        replace(selected, name="maximum_active_videos_15", maximum_active_videos=15),
        replace(selected, name="episode_cooldown_28", episode_cooldown_days=28),
        replace(selected, name="episode_cooldown_56", episode_cooldown_days=56),
        replace(
            selected,
            name=f"recent_window_{14 if selected.recent_window_days == 7 else 7}",
            recent_window_days=14 if selected.recent_window_days == 7 else 7,
        ),
        replace(
            selected,
            name=f"maximum_active_videos_{40 if selected.maximum_active_videos != 40 else 25}",
            maximum_active_videos=40 if selected.maximum_active_videos != 40 else 25,
        ),
        replace(
            selected,
            name=f"minimum_channels_{2 if selected.minimum_channels != 2 else 3}",
            minimum_channels=2 if selected.minimum_channels != 2 else 3,
        ),
    )
    unique: dict[tuple[int, int, int, int], CandidateVariant] = {}
    for variant in candidates:
        key = (
            variant.minimum_channels,
            variant.recent_window_days,
            variant.maximum_active_videos,
            variant.episode_cooldown_days,
        )
        if key != (
            selected.minimum_channels,
            selected.recent_window_days,
            selected.maximum_active_videos,
            selected.episode_cooldown_days,
        ):
            unique.setdefault(key, variant)
    return tuple(unique.values())


def _variant_payload(variant: CandidateVariant) -> dict[str, Any]:
    return {
        "name": variant.name,
        "minimum_channels": variant.minimum_channels,
        "recent_window_days": variant.recent_window_days,
        "maximum_active_videos": variant.maximum_active_videos,
        "episode_cooldown_days": variant.episode_cooldown_days,
    }


def _variant_from_payload(payload: dict[str, Any]) -> CandidateVariant:
    return CandidateVariant(
        name=str(payload["name"]),
        minimum_channels=int(payload["minimum_channels"]),
        recent_window_days=int(payload["recent_window_days"]),
        maximum_active_videos=int(payload["maximum_active_videos"]),
        episode_cooldown_days=int(payload["episode_cooldown_days"]),
    )


def _run_report(
    *,
    eval_dir: Path,
    split: Literal["train", "holdout"],
    output_prefix: str,
    variant: CandidateVariant,
) -> dict[str, Any]:
    artifacts = eval_dir / "artifacts"
    sealed = "_sealed" if split == "holdout" else ""
    command = [
        sys.executable,
        "scripts/run_youniverse_structural_backtest.py",
        "--ai-videos",
        str(artifacts / f"youniverse_ai_{split}{sealed}.jsonl.gz"),
        "--baseline-videos",
        str(artifacts / f"youniverse_baselines_{split}{sealed}.jsonl.gz"),
        "--channel-timeseries",
        str(artifacts / f"youniverse_timeseries_{split}{sealed}.tsv.gz"),
        "--split",
        split,
        "--minimum-channels",
        str(variant.minimum_channels),
        "--recent-window-days",
        str(variant.recent_window_days),
        "--maximum-active-videos",
        str(variant.maximum_active_videos),
        "--episode-cooldown-days",
        str(variant.episode_cooldown_days),
        "--json-output",
        str(artifacts / f"{output_prefix}.json"),
        "--markdown-output",
        str(artifacts / f"{output_prefix}.md"),
    ]
    subprocess.run(command, check=True)
    return json.loads((artifacts / f"{output_prefix}.json").read_text())


def _write_hash_manifest(path: Path, files: list[Path]) -> None:
    rows = [f"{_sha256(file)}  {file.name}" for file in files]
    path.write_text("\n".join(rows) + "\n")


def _verify_hash_manifest(path: Path) -> None:
    for line in path.read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        file = path.parent / name.strip()
        if _sha256(file) != expected:
            raise RuntimeError(f"frozen artifact hash mismatch: {file.name}")


def run_train(eval_dir: Path) -> None:
    artifacts = eval_dir / "artifacts"
    evaluated: list[tuple[CandidateVariant, dict[str, Any]]] = []
    report_files: list[Path] = []
    for variant in (PRIMARY_VARIANT, *FALLBACK_LADDER):
        prefix = f"{CANONICAL_TRAIN}_{variant.name}"
        payload = _run_report(
            eval_dir=eval_dir,
            split="train",
            output_prefix=prefix,
            variant=variant,
        )
        evaluated.append((variant, payload))
        report_files.extend((artifacts / f"{prefix}.json", artifacts / f"{prefix}.md"))
        if is_train_feasible(payload):
            break

    selected = select_train_variant(evaluated)
    selected_prefix = f"{CANONICAL_TRAIN}_{selected.name}"
    shutil.copyfile(artifacts / f"{selected_prefix}.json", artifacts / f"{CANONICAL_TRAIN}.json")
    shutil.copyfile(artifacts / f"{selected_prefix}.md", artifacts / f"{CANONICAL_TRAIN}.md")
    selection = {
        "schema_version": "youniverse-train-policy-selection-v1",
        "frozen_at": datetime.now(tz=UTC).isoformat(),
        "selection_uses_ranking_quality": False,
        "selection_rule": (
            "first preregistered variant with >=50 candidate episodes, >=50 method "
            "predictions and >=80% required episode and future-video baseline coverage; "
            "otherwise primary"
        ),
        "selected": _variant_payload(selected),
        "evaluated": [
            {
                "variant": _variant_payload(variant),
                "feasibility": train_feasibility(payload),
                "report_sha256": _sha256(artifacts / f"{CANONICAL_TRAIN}_{variant.name}.json"),
            }
            for variant, payload in evaluated
        ],
    }
    selection_path = artifacts / SELECTION_FILE
    selection_path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
    canonical = [
        artifacts / f"{CANONICAL_TRAIN}.json",
        artifacts / f"{CANONICAL_TRAIN}.md",
        selection_path,
        *report_files,
    ]
    _write_hash_manifest(artifacts / f"{CANONICAL_TRAIN}.sha256", canonical)


def run_holdout(eval_dir: Path) -> None:
    artifacts = eval_dir / "artifacts"
    train_manifest = artifacts / f"{CANONICAL_TRAIN}.sha256"
    _verify_hash_manifest(train_manifest)
    selection = json.loads((artifacts / SELECTION_FILE).read_text())
    selected = _variant_from_payload(selection["selected"])
    _run_report(
        eval_dir=eval_dir,
        split="holdout",
        output_prefix=CANONICAL_HOLDOUT,
        variant=selected,
    )
    files = [
        artifacts / f"{CANONICAL_HOLDOUT}.json",
        artifacts / f"{CANONICAL_HOLDOUT}.md",
        artifacts / SELECTION_FILE,
    ]
    _write_hash_manifest(artifacts / f"{CANONICAL_HOLDOUT}.sha256", files)


def run_robustness(eval_dir: Path) -> None:
    artifacts = eval_dir / "artifacts"
    holdout_manifest = artifacts / f"{CANONICAL_HOLDOUT}.sha256"
    _verify_hash_manifest(holdout_manifest)
    selection = json.loads((artifacts / SELECTION_FILE).read_text())
    selected = _variant_from_payload(selection["selected"])
    primary = json.loads((artifacts / f"{CANONICAL_HOLDOUT}.json").read_text())
    reports: list[dict[str, Any]] = []
    report_files: list[Path] = []
    for variant in robustness_variants(selected):
        prefix = f"{ROBUSTNESS_PREFIX}_{variant.name}"
        payload = _run_report(
            eval_dir=eval_dir,
            split="holdout",
            output_prefix=prefix,
            variant=variant,
        )
        json_path = artifacts / f"{prefix}.json"
        markdown_path = artifacts / f"{prefix}.md"
        report_files.extend((json_path, markdown_path))
        reports.append(
            {
                "variant": _variant_payload(variant),
                "gate": payload["gate"],
                "metrics": payload["metrics"],
                "report_sha256": _sha256(json_path),
            }
        )
    summary = {
        "schema_version": "youniverse-holdout-robustness-v1",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "primary_was_frozen_before_robustness": True,
        "selected_primary_policy": _variant_payload(selected),
        "primary": {"gate": primary["gate"], "metrics": primary["metrics"]},
        "variants": reports,
    }
    json_output = artifacts / f"{ROBUSTNESS_PREFIX}.json"
    json_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    markdown_rows = [
        "# YouNiverse holdout robustness",
        "",
        "The primary holdout report was hashed before these one-factor checks.",
        "",
        "| Variant | Verdict | Candidates | Precision@10 | Median lead |",
        "|---|---|---:|---:|---:|",
    ]
    for report in reports:
        method = report["metrics"]["rankings"]["method"]
        markdown_rows.append(
            f"| {report['variant']['name']} | {report['gate']['verdict']} | "
            f"{report['metrics']['candidate_topics']} | "
            f"{method['precision_at_10_percent']} | {method['median_lead_days']} |"
        )
    markdown_output = artifacts / f"{ROBUSTNESS_PREFIX}.md"
    markdown_output.write_text("\n".join(markdown_rows) + "\n")
    files = [json_output, markdown_output, holdout_manifest, *report_files]
    _write_hash_manifest(artifacts / f"{ROBUSTNESS_PREFIX}.sha256", files)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", type=Path, default=Path("/eval"))
    parser.add_argument("--split", choices=("train", "holdout", "robustness"), required=True)
    args = parser.parse_args()
    if args.split == "train":
        run_train(args.eval_dir)
    elif args.split == "holdout":
        run_holdout(args.eval_dir)
    else:
        run_robustness(args.eval_dir)


if __name__ == "__main__":
    main()
