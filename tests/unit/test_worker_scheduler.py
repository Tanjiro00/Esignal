from apps.worker.__main__ import _parser


def test_serve_uses_separate_ingestion_and_snapshot_batch_limits() -> None:
    args = _parser().parse_args(["serve"])

    assert args.limit == 5
    assert args.snapshot_limit == 50
    assert args.poll_seconds == 60
