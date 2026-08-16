"""Turn the panel export into a CRM-ready lead sheet.

The playbook asks for a table with one row per lead and a "next touch" date on
every non-terminal row. It also asks the founder to hunt for an X handle by
hand; most channels put theirs in the description, so that lookup is done here
instead — anything found is a starting point to verify, never a guarantee.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

RAW = Path(__file__).parent / "leads_raw.csv"
CRM = Path(__file__).parent / "leads_crm.csv"
TOP = Path(__file__).parent / "leads_top50.csv"

# Handles that appear in descriptions but belong to platforms, not to the
# creator: matching them would fill the sheet with dead contacts.
NOT_A_HANDLE = {
    "youtube",
    "instagram",
    "facebook",
    "tiktok",
    "twitter",
    "x",
    "discord",
    "patreon",
    "linkedin",
    "github",
    "reddit",
    "twitch",
    "threads",
    "home",
    "watch",
    "channel",
    "user",
    "c",
    "shorts",
    "playlist",
    "intent",
    "share",
}

X_URL = re.compile(r"(?:twitter\.com|x\.com)/(?:#!/)?@?([A-Za-z0-9_]{2,15})", re.I)
AT_HANDLE = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{3,15})\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")

HEADER = [
    "channel",
    "subs",
    "videos_90d",
    "comments_30d",
    "last_upload",
    "url",
    "x_handle",
    "x_confidence",
    "email",
    "hook",
    "report_url",
    "status",
    "last_touch",
    "next_touch",
    "notes",
]


def x_handle(description: str) -> tuple[str, str]:
    """Pick the creator's own handle, not a sponsor or a mentioned person.

    Taking the first handle in the text is wrong: it returned @OpenAI for one
    channel and @rauchg (Vercel's CEO) for another, because both were merely
    mentioned. A creator's own handle repeats across every video description
    ("follow me on X"), while a mention appears once.

    So candidates are counted across the concatenated descriptions and the most
    frequent wins. A handle seen once is returned as `low` confidence and must
    be verified before use; two or more occurrences is `ok`.
    """

    counts: Counter[str] = Counter()
    for pattern in (X_URL, AT_HANDLE):
        for match in pattern.finditer(description):
            handle = match.group(1)
            if handle.lower() not in NOT_A_HANDLE:
                counts[handle] += 1
    if not counts:
        return "", ""
    handle, seen = counts.most_common(1)[0]
    return f"@{handle}", "ok" if seen >= 2 else "low"


def email(description: str) -> str:
    found = EMAIL.search(description)
    return found.group(0) if found else ""


def main() -> None:
    if not RAW.exists():
        sys.exit(f"missing {RAW}")
    rows = []
    with RAW.open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # the export header carries SQL expression names
        for row in reader:
            if len(row) < 7:
                continue
            title, subs, videos, comments, url, last_upload, description = row[:7]
            handle, confidence = x_handle(description)
            rows.append(
                {
                    "channel": title,
                    "subs": int(subs or 0),
                    "videos_90d": int(videos or 0),
                    "comments_30d": int(comments or 0),
                    "last_upload": last_upload,
                    "url": url,
                    "x_handle": handle,
                    "x_confidence": confidence,
                    "email": email(description),
                    "hook": "",
                    "report_url": "",
                    "status": "lead",
                    "last_touch": "",
                    "next_touch": "",
                    "notes": "",
                }
            )

    # Comment volume first: a fat comment section makes a fat report, which is
    # the whole first touch.
    rows.sort(key=lambda item: (-item["comments_30d"], -item["subs"]))

    for path, subset in ((CRM, rows), (TOP, rows[:50])):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(subset)

    with_x = sum(1 for row in rows if row["x_confidence"] == "ok")
    with_email = sum(1 for row in rows if row["email"])
    reachable = sum(1 for row in rows if row["x_confidence"] == "ok" or row["email"])
    print(f"leads: {len(rows)}")
    low = sum(1 for row in rows if row["x_confidence"] == "low")
    print(f"  X handle (ok) : {with_x} ({with_x / len(rows) * 100:.0f}%)")
    print(f"  X handle (low): {low} — verify before using")
    print(f"  with email    : {with_email} ({with_email / len(rows) * 100:.0f}%)")
    print(f"  reachable     : {reachable} ({reachable / len(rows) * 100:.0f}%)")
    print(f"  median subs   : {sorted(r['subs'] for r in rows)[len(rows) // 2]:,}")
    print(f"wrote {CRM.name} and {TOP.name}")


if __name__ == "__main__":
    main()
