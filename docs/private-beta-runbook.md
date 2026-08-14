# First workspace setup

This runbook creates the first private-beta tenant without direct database
access. The current production context intentionally assumes one founder
workspace per deployment.

## 1. Create the workspace and owner

```bash
curl --fail-with-body \
  -H 'Content-Type: application/json' \
  -d '{
    "workspace_name": "Creator Studio",
    "timezone": "Europe/Moscow",
    "owner_email": "owner@example.com",
    "owner_name": "Owner"
  }' \
  https://api.earlysignal.example.com/api/v1/admin/workspaces
```

Save the returned `workspace_id` and open the returned onboarding path on the
web hostname. The API is private-beta founder administration and must be
protected by the deployment proxy until application authentication is added.

## 2. Complete onboarding

1. Confirm workspace name and IANA timezone.
2. Add the owned YouTube channel ID or canonical `/channel/UC…` URL. EarlySignal
   previews recent uploads and infers topics, format, and normal duration.
3. Add at least three reference or competitor channels in Watchlists.
4. Review the seeded discovery queries in Admin → Providers and run the first
   ingestion.
5. Review the owned-channel profile in Settings.
6. Prepare the in-app digest and complete setup.

## 3. Build the first evidence set

```bash
make seed-queries
make ingest-real
make refresh-video-intelligence
make run-snapshots
make build-signals
make refresh-demand
make refresh-transcripts
make generate-digest WORKSPACE_ID=the-returned-workspace-id
```

Open Signals and confirm that live topics are based on at least two videos from
two independent channels. Open each top signal and inspect provenance before
using its recommended angle.

## 4. Acceptance check

- Onboarding reports all five steps complete.
- Pulse shows current signal/discovery/snapshot freshness.
- Digest contains up to three current signals with source video links,
  demand, saturation/timing, and Act/Watch/Skip guidance.
- A signal can be saved, converted to a brief, and linked to a published
  outcome.
- Admin → Operations exposes no critical alert and a verified recovery point.
- Admin → Providers shows at least one ready route for every required
  capability.

Take and verify the first backup before inviting the beta user.
