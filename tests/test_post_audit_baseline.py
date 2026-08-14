from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps.api.main import app

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "evaluation" / "post-audit-baseline.json"


def _canonical_hash(payload: dict[str, object]) -> str:
    content = dict(payload)
    expected = content.pop("content_sha256")
    assert isinstance(expected, str)
    actual = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert actual == expected
    return actual


def test_post_audit_baseline_is_self_consistent() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())

    assert payload["fixture_version"] == "post-audit-baseline-v1"
    assert payload["product_behavior_changed"] is False
    assert payload["release_policy"]["mandatory_human_review"] is False
    assert payload["release_policy"]["production_review_queue_enabled"] is False
    assert payload["feature_flags"]["production_disabled"] == ["FEATURE_SIGNAL_REVIEW_QUEUE"]
    assert payload["privacy"] == {
        "secrets_included": False,
        "raw_payloads_included": False,
        "comment_text_included": False,
        "credentials_included": False,
    }
    _canonical_hash(payload)
    for source in payload["authoritative_inputs"]:
        path = ROOT / source["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_post_audit_visual_baseline_files_match() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())
    screenshots = payload["visual_baseline"]["screenshots"]

    assert len(screenshots) == 14
    assert payload["visual_baseline"]["mobile_horizontal_overflow"] is False
    for screenshot in screenshots:
        path = ROOT / screenshot["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == screenshot["sha256"]
        assert screenshot["width"] in {390, 1440}
        assert screenshot["height"] in {844, 1000}


def test_post_audit_openapi_inventory_matches_current_app() -> None:
    payload = json.loads(FIXTURE_PATH.read_text())
    contract = payload["api_contract"]
    schema = app.openapi()
    operations = [
        {
            "method": method.upper(),
            "path": path,
            "operation_id": specification.get("operationId"),
        }
        for path, methods in sorted(schema["paths"].items())
        for method, specification in sorted(methods.items())
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    ]
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()

    assert contract["prefix"] == "/api/v1"
    assert contract["operation_count"] == len(operations) == 96
    assert contract["operations"] == operations
    assert contract["openapi_sha256"] == hashlib.sha256(canonical).hexdigest()
