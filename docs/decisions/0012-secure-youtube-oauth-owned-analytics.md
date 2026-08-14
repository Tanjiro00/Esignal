# ADR 0012: YouTube OAuth is optional, encrypted, and read only

- Status: Accepted
- Date: 2026-07-29

## Context

Public channel history supports estimated fit, but verified personalization and
outcome tracking require owned analytics. OAuth failure must not make the
private beta unusable or expose long-lived credentials.

## Decision

YouTube OAuth uses authorization code flow with PKCE, a ten-minute single-use
state, an exact redirect URI, and read-only YouTube Data, Analytics, and
Analytics Monetary scopes. The authorized YouTube channel must match the
workspace’s configured owned channel.

Access tokens, refresh tokens, and temporary PKCE verifiers are encrypted with
Fernet before database storage. The encryption key and Google client secret are
server-only settings. Audit rows contain event types, safe result codes, scope
names, and channel IDs; they never contain credentials or remote response
bodies.

`youtube-owned-analytics-v1` imports views, watch time, average view duration,
average percentage viewed, subscribers gained, traffic-source groups,
geography, and revenue where granted, alongside content type, publish date, and
duration. Active connections sync at most every six hours by default.

Channel fit remains `estimated` until owned metrics exist, then becomes
`verified`. Refresh and analytics errors set a degraded status while public
history and all non-OAuth product paths continue to work. Disconnect attempts
remote revocation, clears encrypted token values, and retains only the audit
record.

## Consequences

- Demo mode and private-beta workspaces do not require OAuth credentials.
- Token rotation or an encryption-key change requires an explicit migration or
  reconnect; silent fallback to plaintext is forbidden.
- Revenue access is still read only but requires the monetary analytics scope.
- Verified analytics can improve channel fit and outcome metrics without
  changing deterministic global trend scores.
