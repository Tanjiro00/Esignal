from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    ProviderBenchmarkRun,
    ProviderFetch,
    ProviderRoutingDecision,
    YoutubeVideo,
)
from apps.api.provider_operations import SqlAlchemyProviderFetchRecorder
from packages.domain import DiscoveryQuery
from packages.provider_sdk.youtube_comments_web import YoutubeWebCommentProvider
from packages.provider_sdk.youtube_official import YoutubeOfficialProvider
from packages.provider_sdk.youtube_transcript import YoutubeTranscriptProvider
from packages.provider_sdk.youtube_web import YoutubeWebDiscoveryProvider

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPOSITORY_ROOT / "fixtures" / "provider_benchmark.yaml"
BENCHMARK_VERSION = "provider-benchmark-v1"


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


class ProviderBenchmarkService:
    """Runs bounded raw-provider probes and reports reproducible operational metrics."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._recorder = SqlAlchemyProviderFetchRecorder(session, settings)

    async def run(
        self,
        *,
        live: bool = False,
        limit: int = 3,
        fixture_path: Path = DEFAULT_FIXTURE,
    ) -> ProviderBenchmarkRun:
        started_at = datetime.now(tz=UTC)
        fixture = self.load_fixture(fixture_path)
        queries = self.expand_queries(fixture)
        run = ProviderBenchmarkRun(
            id=str(uuid4()),
            benchmark_version=str(fixture["version"]),
            fixture_path=str(fixture_path.relative_to(REPOSITORY_ROOT)),
            started_at=started_at,
            completed_at=None,
            status="running",
            live_case_count=0,
            result_json={},
            recommended_priorities_json={},
            json_path=None,
            csv_path=None,
            markdown_path=None,
            error_code=None,
            error_message=None,
        )
        self._session.add(run)
        self._session.commit()
        try:
            live_results = (
                await self._run_live_cases(queries=queries, limit=max(1, min(limit, 20)))
                if live
                else []
            )
            metrics = self._aggregate_metrics(since=started_at - timedelta(days=30))
            recommendations = self._recommend(metrics)
            result = {
                "benchmark_version": fixture["version"],
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "mode": "live" if live else "stored_observations",
                "fixture": {
                    "query_count": len(queries),
                    "corpus_targets": fixture["corpus_targets"],
                },
                "live_cases": live_results,
                "metrics": metrics,
                "recommended_priorities": recommendations,
                "cost_scenarios": self._cost_scenarios(metrics),
                "metric_coverage": {
                    "measured": [
                        "request_count",
                        "success_rate",
                        "error_rate",
                        "p50_latency_ms",
                        "p95_latency_ms",
                        "entity_yield",
                        "duplicate_rate",
                        "cost_per_success",
                        "fallback_rate",
                    ],
                    "requires_labeled_corpus": [
                        "precision_at_20",
                        "caption_word_error_rate",
                        "comment_recall",
                    ],
                },
                "caveats": [
                    "YouTube API quota units are tracked separately from USD; "
                    "current adapters report zero direct USD cost.",
                    "Precision, transcript accuracy, and comment recall need a "
                    "human-labeled gold set and are intentionally not inferred.",
                    "Stored-observation mode reflects the last 30 days of real provider "
                    "traffic; live mode adds bounded raw probes only.",
                ],
            }
            paths = self._write_outputs(run.id, result)
            run.completed_at = datetime.now(tz=UTC)
            run.status = "success" if metrics else "preliminary"
            run.live_case_count = len(live_results)
            run.result_json = result
            run.recommended_priorities_json = recommendations
            run.json_path = paths["json"]
            run.csv_path = paths["csv"]
            run.markdown_path = paths["markdown"]
            self._session.commit()
            return run
        except Exception as error:
            run.completed_at = datetime.now(tz=UTC)
            run.status = "failed"
            run.error_code = type(error).__name__
            run.error_message = str(error)[:1000]
            self._session.commit()
            raise

    @staticmethod
    def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
        fixture = cast(dict[str, Any], json.loads(path.read_text()))
        if fixture.get("version") != BENCHMARK_VERSION:
            raise ValueError("Unsupported provider benchmark fixture version")
        required = {"base_topics", "query_templates", "corpus_targets", "live_defaults"}
        if not required.issubset(fixture):
            raise ValueError("Provider benchmark fixture is incomplete")
        queries = ProviderBenchmarkService.expand_queries(fixture)
        expected = int(fixture["corpus_targets"]["queries"])
        if len(queries) != expected:
            raise ValueError(
                f"Benchmark fixture expands to {len(queries)} queries, expected {expected}"
            )
        return fixture

    @staticmethod
    def expand_queries(fixture: dict[str, Any]) -> list[str]:
        return [
            str(template).format(topic=topic)
            for topic in fixture["base_topics"]
            for template in fixture["query_templates"]
        ]

    async def _run_live_cases(
        self,
        *,
        queries: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        web = YoutubeWebDiscoveryProvider(recorder=self._recorder)
        discovery_providers: list[Any] = [web]
        official = YoutubeOfficialProvider(
            api_key=self._settings.youtube_api_key,
            recorder=self._recorder,
        )
        if self._settings.youtube_api_key:
            discovery_providers.append(official)
        for query_text in queries[:limit]:
            for provider in discovery_providers:
                case = {
                    "capability": "discovery",
                    "provider": provider.name,
                    "case": query_text,
                    "status": "success",
                    "result_count": 0,
                    "error": None,
                }
                try:
                    items = await provider.search(
                        DiscoveryQuery(
                            query=query_text,
                            country="US",
                            language="en",
                            published_after=datetime.now(tz=UTC) - timedelta(days=14),
                            max_results=20,
                        )
                    )
                    case["result_count"] = len(items)
                except Exception as error:
                    case["status"] = "failed"
                    case["error"] = getattr(error, "reason", type(error).__name__)
                cases.append(case)

        video_ids = list(
            self._session.scalars(
                select(YoutubeVideo.youtube_video_id)
                .where(~YoutubeVideo.youtube_video_id.startswith("esdemo"))
                .order_by(desc(YoutubeVideo.first_discovered_at))
                .limit(limit)
            )
        )
        comment_providers: list[Any] = [YoutubeWebCommentProvider(recorder=self._recorder)]
        if self._settings.youtube_api_key:
            comment_providers.insert(0, official)
        transcript = YoutubeTranscriptProvider(recorder=self._recorder)
        for video_id in video_ids:
            for provider in comment_providers:
                cases.append(await self._probe_comments(provider, video_id))
            cases.append(await self._probe_transcript(transcript, video_id))
        return cases

    async def _probe_comments(self, provider: Any, video_id: str) -> dict[str, Any]:
        case = {
            "capability": "comments",
            "provider": provider.name,
            "case": video_id,
            "status": "success",
            "result_count": 0,
            "error": None,
        }
        try:
            items = await provider.fetch_comments(
                video_id,
                order="relevance",
                limit=30,
                include_replies=False,
            )
            case["result_count"] = len(items)
        except Exception as error:
            case["status"] = "failed"
            case["error"] = getattr(error, "reason", type(error).__name__)
        return case

    async def _probe_transcript(
        self,
        provider: YoutubeTranscriptProvider,
        video_id: str,
    ) -> dict[str, Any]:
        case = {
            "capability": "transcripts",
            "provider": provider.name,
            "case": video_id,
            "status": "success",
            "result_count": 0,
            "error": None,
        }
        try:
            transcript = await provider.fetch_transcript(
                video_id,
                preferred_languages=("en", "en-US", "en-GB"),
                allow_generated=False,
            )
            case["result_count"] = len(transcript.segments)
        except Exception as error:
            case["status"] = "failed"
            case["error"] = getattr(error, "reason", type(error).__name__)
        return case

    def _aggregate_metrics(self, *, since: datetime) -> list[dict[str, Any]]:
        rows = list(
            self._session.scalars(
                select(ProviderFetch).where(
                    ProviderFetch.started_at >= since,
                    ~ProviderFetch.provider.startswith("mock_"),
                )
            )
        )
        grouped: defaultdict[tuple[str, str], list[ProviderFetch]] = defaultdict(list)
        for row in rows:
            grouped[(row.capability, row.provider)].append(row)
        decisions = list(
            self._session.scalars(
                select(ProviderRoutingDecision).where(ProviderRoutingDecision.created_at >= since)
            )
        )
        metrics: list[dict[str, Any]] = []
        for (capability, provider), fetches in sorted(grouped.items()):
            successes = [item for item in fetches if item.status == "success"]
            latencies = [item.latency_ms for item in fetches]
            linked = [entity_id for item in successes for entity_id in item.linked_entity_ids]
            selected = [
                item
                for item in decisions
                if item.capability == capability and item.selected_provider == provider
            ]
            fallback_rate = (
                sum(item.fallback_used for item in selected) / len(selected) * 100
                if selected
                else 0
            )
            actual_cost = sum(item.actual_cost for item in fetches)
            metrics.append(
                {
                    "capability": capability,
                    "provider": provider,
                    "request_count": len(fetches),
                    "success_rate": round(len(successes) / len(fetches) * 100, 2),
                    "error_rate": round(
                        (len(fetches) - len(successes)) / len(fetches) * 100,
                        2,
                    ),
                    "p50_latency_ms": round(median(latencies)) if latencies else 0,
                    "p95_latency_ms": _percentile(latencies, 0.95),
                    "entity_yield": round(len(linked) / len(successes), 2) if successes else 0,
                    "duplicate_rate": round(
                        (len(linked) - len(set(linked))) / len(linked) * 100,
                        2,
                    )
                    if linked
                    else 0,
                    "fallback_rate": round(fallback_rate, 2),
                    "actual_cost_usd": round(actual_cost, 6),
                    "cost_per_success_usd": round(
                        actual_cost / len(successes),
                        6,
                    )
                    if successes
                    else 0,
                }
            )
        return metrics

    @staticmethod
    def _recommend(metrics: list[dict[str, Any]]) -> dict[str, list[str]]:
        grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for metric in metrics:
            grouped[str(metric["capability"])].append(metric)
        return {
            capability: [
                str(item["provider"])
                for item in sorted(
                    rows,
                    key=lambda item: (
                        -float(item["success_rate"]),
                        float(item["actual_cost_usd"]),
                        int(item["p95_latency_ms"]),
                    ),
                )
            ]
            for capability, rows in grouped.items()
        }

    @staticmethod
    def _cost_scenarios(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_requests = sum(int(item["request_count"]) for item in metrics)
        total_cost = sum(float(item["actual_cost_usd"]) for item in metrics)
        unit_cost = total_cost / total_requests if total_requests else 0
        return [
            {
                "name": name,
                "monthly_requests": requests,
                "estimated_cost_usd": round(unit_cost * requests, 2),
            }
            for name, requests in (
                ("starter", 1_000),
                ("growth", 10_000),
                ("scale", 100_000),
            )
        ]

    def _write_outputs(
        self,
        run_id: str,
        result: dict[str, Any],
    ) -> dict[str, str]:
        output = REPOSITORY_ROOT / self._settings.provider_benchmark_output_directory
        output.mkdir(parents=True, exist_ok=True)
        stem = f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-{run_id[:8]}"
        json_path = output / f"{stem}.json"
        csv_path = output / f"{stem}.csv"
        markdown_path = output / f"{stem}.md"
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        with csv_path.open("w", newline="") as handle:
            metrics = result["metrics"]
            fieldnames = list(metrics[0]) if metrics else ["capability", "provider"]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metrics)
        markdown = self._markdown(result)
        markdown_path.write_text(markdown)
        docs_path = REPOSITORY_ROOT / "docs" / "provider-benchmark.md"
        docs_path.write_text(markdown)
        return {
            "json": str(json_path.relative_to(REPOSITORY_ROOT)),
            "csv": str(csv_path.relative_to(REPOSITORY_ROOT)),
            "markdown": str(markdown_path.relative_to(REPOSITORY_ROOT)),
        }

    @staticmethod
    def _markdown(result: dict[str, Any]) -> str:
        lines = [
            "# Provider benchmark",
            "",
            f"Generated: {result['generated_at']}",
            f"Mode: {result['mode']}",
            f"Fixture corpus: {result['fixture']['query_count']} discovery queries.",
            "",
            "## Recommended priority",
            "",
        ]
        for capability, providers in result["recommended_priorities"].items():
            lines.append(f"- **{capability}:** {' → '.join(providers)}")
        if not result["recommended_priorities"]:
            lines.append("- Preliminary: no real provider observations are available yet.")
        lines.extend(
            [
                "",
                "## Metrics",
                "",
                "| Capability | Provider | Requests | Success | p50 | p95 | Yield | Fallback |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in result["metrics"]:
            lines.append(
                f"| {item['capability']} | {item['provider']} | "
                f"{item['request_count']} | {item['success_rate']}% | "
                f"{item['p50_latency_ms']} ms | {item['p95_latency_ms']} ms | "
                f"{item['entity_yield']} | {item['fallback_rate']}% |"
            )
        lines.extend(["", "## Caveats", ""])
        lines.extend(f"- {item}" for item in result["caveats"])
        lines.append("")
        return "\n".join(lines)
