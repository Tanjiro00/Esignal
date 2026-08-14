"""Collect viewer comments across the panel.

Comments are the evidence the product sells: a demand item is a group of real
viewers asking the same unanswered question. Coverage therefore has to follow
the panel, not the old v1 signal — under the previous selection a video could
only get its comments read if a scorer that never worked had already flagged it.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict

from apps.api.config import Settings, get_settings
from apps.api.database import SessionLocal
from apps.worker.demand_intelligence import DemandIntelligenceService


async def run(settings: Settings, *, limit: int, selection: str, dry_run: bool) -> None:
    with SessionLocal() as session:
        service = DemandIntelligenceService(session, settings)
        panel = len(service.select_panel_candidates(limit=limit))
        signal = len(service.select_candidates(limit=limit))
        print(f"candidates: panel={panel} signal={signal} (limit={limit})")
        if dry_run:
            print("dry run; pass --apply to fetch")
            return
        result = await service.run(force=True, limit=limit, selection=selection)
        for key, value in asdict(result).items():
            print(f"  {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--selection", choices=("panel", "signal"), default="panel")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    asyncio.run(
        run(
            get_settings(),
            limit=args.limit,
            selection=args.selection,
            dry_run=not args.apply,
        )
    )


if __name__ == "__main__":
    main()
