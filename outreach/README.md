# Outreach kit

Everything needed to start the playbook's first five days. Built from the
production panel on 2026-08-16.

| File | What it is |
|---|---|
| `leads_crm.csv` | 437 Tier-1 leads, CRM columns, ready to paste into Google Sheets |
| `leads_top50.csv` | the same sheet cut to the 50 fattest comment sections |
| `MESSAGES_EN.md` | DM, email, follow-ups, call script, objections |
| `build_leads.py` | rebuilds both sheets from a fresh export |
| `leads.sql` | the export query |

---

## The lead list

Filters follow the playbook: 10k–300k subscribers, at least six uploads in 90
days, sorted by comments in the last 30 days — a fat comment section makes a
fat report, and the report is the first touch.

```
437 leads   median 51,300 subs
 56 with an X handle that repeats across descriptions   (13%)
 52 with a handle seen once — verify first              (12%)
139 with an email in a description                      (32%)
177 reachable without manual lookup                     (41%)
```

Top 50: 27 already have a reliable contact.

### About `x_confidence`

Taking the first handle found in a description is wrong. It produced `@OpenAI`
for one channel and `@rauchg` — Vercel's CEO — for another, because both were
merely mentioned in the text.

A creator's own handle repeats across every video description ("follow me on
X"); a mention appears once. So handles are counted and the most frequent wins:

- `ok` — the handle repeats. Most likely theirs.
- `low` — seen once. Most likely someone they mentioned.
- empty — nothing found; use the channel's About page.

**`ok` means "repeated", not "verified".** Both still deserve a five-second
look at the channel page before you send anything. Sending a DM to the wrong
person costs more than the minute it takes to check.

---

## Day 1 — set up

1. Import `leads_top50.csv` into a Google Sheet. Column order already matches
   the playbook: channel, subs, videos_90d, comments_30d, last_upload, url,
   x_handle, x_confidence, email, hook, report_url, status, last_touch,
   next_touch, notes.
2. Confirm contacts for the first 20 rows. Where `x_handle` is empty, open the
   channel → About → "View email address" (needs a Google login).
3. Freeze the rule: every row not in a terminal status must always carry a
   `next_touch` date. An empty one means the lead is lost.

Statuses: `lead → report_ready → contacted → replied → call_booked →
pilot_offered → pilot_active → paid / closed_lost / closed_no_reply`.

## Day 2 — reports

Generate through the admin surface at `/admin/outreach`, or the API:

```bash
# create (async; returns 202)
curl -X POST https://<host>/api/v1/admin/outreach \
  -H 'Content-Type: application/json' -b "$SESSION" \
  -d '{"channel_input": "https://www.youtube.com/channel/UC..."}'

# list, then approve or reject each one
curl https://<host>/api/v1/admin/outreach -b "$SESSION"
curl -X POST https://<host>/api/v1/admin/outreach/<id>/approve -b "$SESSION"
```

Approved reports are readable at `/r/{token}` and as `/r/{token}.pdf`. Links
expire, and `/revoke` kills one early.

**Review every report by eye before it leaves.** For each of the ≤3 findings:
is it genuinely relevant to this channel, is it genuinely not covered by their
own videos, are the quotes real? Any doubt — drop the finding. Nothing worth
keeping — the lead waits rather than receiving junk.

Expect 6–8 usable reports out of 10. That is normal.

Write the strongest finding into the `hook` column as one line:
`14 people asked how you'd run Qwen locally on 16GB — under 3 of your videos`.

## Days 3–5 — touches

8–10 first touches a day from `MESSAGES_EN.md`. Reply to anyone who says yes
within the hour; speed decides. Friday: compare hooks that got replies against
hooks that did not, and change exactly one thing in the template.

Rhythm: 40–50 touches a week. The funnel the playbook expects:

```
100 touches → 20–30 replies → 10–15 "send it" → 6–10 calls → 3–5 pilots
```

If replies stay under 10% after 150 touches, the hooks are too thin. Fix the
product, not the volume.

---

## Refreshing the list

```bash
# on the server: run the export
docker cp outreach/leads.sql earlysignal-postgres-1:/tmp/leads.sql
docker exec earlysignal-postgres-1 \
  psql -U earlysignal -d earlysignal -f /tmp/leads.sql > leads_raw.csv

# locally: rebuild the sheets
uv run python outreach/build_leads.py
```

Rebuild monthly, or after the panel grows. Keep the old sheet — statuses and
touch dates live there, not in the export.

---

## What this kit does not include

- **Tier 2 (agencies).** The playbook wants them from week two, found by X bio
  search ("YouTube strategist", "we grow tech channels") and by the
  "edited/managed by" lines in creator video descriptions. Not extractable from
  the panel, which holds channels rather than the people behind them.
- **Verified contacts.** Everything here is a starting point mined from public
  descriptions.
- **Sending.** No automation on purpose: the playbook's whole thesis is that ten
  personal messages beat a hundred templated ones.
