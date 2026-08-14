import os
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    port = os.environ.get("PORT", "8000")
    database_path = root / "earlysignal-e2e.db"
    if database_path.exists():
        database_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
    os.environ["DEMO_MODE"] = "true"
    os.environ["FEATURE_EARLYNESS_TIMELINE"] = "true"
    os.environ["FEATURE_SIGNAL_REVIEW_QUEUE"] = "true"
    os.environ["FEATURE_COMMENT_TOPIC_RELEVANCE"] = "true"
    os.environ["FEATURE_DECISION_EXPERIENCE"] = "true"
    os.environ["FEATURE_MICROTOPIC_CONTENT_GAP"] = "true"
    os.environ["FEATURE_FEEDBACK_EVALUATION"] = "true"
    os.environ["FEATURE_TOPIC_SNAPSHOT_BUCKETS"] = "true"
    os.environ["FEATURE_CHANNEL_PROFILE_FEASIBILITY_V2"] = "true"
    os.environ["FEATURE_OUTCOME_SUGGESTIONS"] = "true"
    os.environ["FEATURE_SIGNAL_PACKAGING"] = "true"
    os.environ["FEATURE_QUERY_EXPANSION"] = "true"
    for flag in (
        "FEATURE_UX_TODAY_HOME_V1",
        "FEATURE_UX_DECISION_CARD_V1",
        "FEATURE_UX_SIMPLE_SCORES_V1",
        "FEATURE_UX_SIMPLIFIED_NAVIGATION_V1",
        "FEATURE_UX_ONBOARDING_V2",
        "FEATURE_UX_OPPORTUNITY_DETAIL_V2",
        "FEATURE_UX_BRIEF_V2",
        "FEATURE_UX_RESULTS_V2",
    ):
        os.environ[flag] = "true"
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=root, check=True)
    subprocess.run(["uv", "run", "python", "-m", "apps.api.seed"], cwd=root, check=True)
    os.execvp(
        "uv",
        [
            "uv",
            "run",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
