"""Build the stored demand feed."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from apps.api.config import get_settings
from apps.api.database import SessionLocal
from apps.worker.demand_feed import DemandFeedService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=30)
    parser.add_argument("--embed-limit", type=int, default=2000)
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as session:
        service = DemandFeedService(session, get_settings())
        result = service.run(
            window_days=args.window,
            embed_limit=args.embed_limit,
            verify=not args.no_verify,
        )
    for key, value in asdict(result).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
