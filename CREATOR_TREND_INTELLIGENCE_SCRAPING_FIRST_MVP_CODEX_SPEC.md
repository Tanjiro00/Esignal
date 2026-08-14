# Creator Trend Intelligence — Scraping-First MVP Codex Specification

**Working codename:** EarlySignal  
**Target market:** United States  
**Initial platform:** English-language YouTube  
**Initial vertical:** AI / technology creators  
**Status:** Aggressive MVP / private beta specification  
**Last updated:** 2026-07-26  
**Supersedes for MVP execution:** `CREATOR_TREND_INTELLIGENCE_CODEX_SPEC.md` where the two documents conflict

---

## 0. Mission for Codex

Build a working private-beta product that continuously discovers emerging YouTube topics, measures their momentum before they become saturated, mines comments for unmet audience demand, and turns the evidence into channel-specific content opportunities.

The purpose of this MVP is not to prove that the product can comply with every platform policy at enterprise scale. The purpose is to prove that:

1. the system can find useful signals earlier than manual research;
2. creator teams will repeatedly act on those signals;
3. videos produced from those signals outperform the channel's normal baseline;
4. at least several US customers will pay for continued access.

The MVP must prioritize **speed, coverage, product learning, and data quality** over perfect platform purity.

Do not turn this into a generic analytics dashboard, keyword tool, thumbnail tool, or content generator.

---

# 1. Non-negotiable execution rules

1. Build for **YouTube only**.
2. Build for **English-language AI/tech content only**.
3. Treat third-party data providers and scraping services as first-class production dependencies for the MVP.
4. Do not make the official YouTube Data API a prerequisite for discovery, transcripts, or comments.
5. The official YouTube API may be used for cheap canonical metadata and statistics when available.
6. All providers must sit behind stable internal interfaces.
7. Never allow provider-specific response shapes to leak into product logic.
8. Store the raw provider payload for every successful ingestion result.
9. Store provenance for every normalized field.
10. Deduplicate globally by canonical YouTube `video_id` and `channel_id`.
11. Preserve historical snapshots; do not overwrite view counts or engagement metrics.
12. Every trend claim shown to a user must be traceable to videos, comments, snapshots, or transcript segments.
13. LLMs may summarize evidence but may not invent evidence.
14. Data collection must degrade gracefully when one provider fails.
15. Implement retries, circuit breakers, provider health metrics, and cost caps from the beginning.
16. Do not build custom CAPTCHA solving, browser fingerprint spoofing, credential theft, account farming, or key-pooling systems.
17. Direct scraping code is allowed only as an optional fallback adapter and must be isolated from the rest of the system.
18. Use public content only in the MVP.
19. Do not collect private, membership-only, login-required, or age-gated content.
20. Do not store more personal data about commenters than needed for clustering and evidence.
21. Optimize for 20–50 design partners, not global scale.
22. A partially manual operation is acceptable if it helps prove demand faster.
23. Do not add TikTok, Instagram, X, Reddit, podcasts, newsletters, or Google Trends to the core product before the YouTube loop works.
24. Do not implement billing until a creator has acted on a signal or the founder explicitly asks for billing.
25. Do not add features outside this specification without documenting why they are required.

---

# 2. Product thesis

Existing creator tools are good at showing:

- videos that already went viral;
- channel outliers;
- keyword popularity;
- competitor uploads;
- successful titles and thumbnails.

EarlySignal should identify **topic formation before the obvious breakout**.

The strongest signal is not one viral video. It is a topic beginning to spread across several independent channels while viewers ask similar unanswered questions and large channels have not yet saturated the topic.

The product should answer:

1. What topic is starting to accelerate?
2. Which independent creators are carrying the signal?
3. How quickly is the topic spreading?
4. Is the opportunity early, breaking out, or saturated?
5. What audience questions remain unanswered?
6. Does this topic fit the user's channel?
7. How much time remains to publish?
8. What concrete angle should the creator make?

## 2.1 Core promise

> Find emerging YouTube topics before they become obvious, understand what viewers still want, and turn the evidence into a video your channel can publish in time.

## 2.2 Initial customer

Primary:

- English-language YouTube creator teams;
- 100,000–5,000,000 subscribers;
- AI, software, consumer technology, productivity, tech business, or adjacent coverage;
- at least two videos per month;
- can react within 3–14 days;
- has a researcher, strategist, writer, producer, or channel operator.

Secondary:

- agencies managing at least five channels;
- technology media teams;
- B2B content studios;
- newsletters with a YouTube operation.

Not for MVP:

- brand-new creators;
- evergreen-only channels;
- entertainment niches requiring deep visual understanding;
- users seeking fully automated spam channels;
- users who only need SEO keywords.

---

# 3. MVP success criteria

The product is not validated because it has a polished dashboard.

The product is validated when the following loop occurs:

```text
signal detected
→ user opens evidence
→ user saves or accepts signal
→ content brief created
→ user publishes video
→ outcome linked
→ video beats channel baseline or produces a strong qualitative win
```

## 3.1 Day-45 target

- at least 10 active design partners;
- at least 5 users open the product weekly;
- at least 15 signals saved;
- at least 5 content briefs created;
- at least 2 videos published from product signals.

## 3.2 Day-90 target

- 20–30 active design partners;
- 8–12 paying customers or signed paid pilots;
- 10+ videos published from signals;
- at least 3 credible case studies;
- median weekly signal-open rate above 35%;
- at least 20% of high-confidence signals saved, briefed, or dismissed with structured feedback;
- evidence that the system has meaningful lead time over obvious breakout tools.

## 3.3 North-star metric

`published_videos_from_signals_per_active_workspace_per_month`

Supporting metric:

`successful_published_videos_from_signals_per_active_workspace_per_month`

A successful published video is one that exceeds a workspace-defined performance threshold, for example:

- 1.5× normal seven-day views;
- top 25% of recent uploads;
- above-baseline views per hour;
- a strong user-confirmed strategic outcome.

---

# 4. Scope

## 4.1 In scope

- workspace and user authentication;
- onboarding a creator channel;
- selecting competitor/reference channels;
- configuring topic/query universes;
- provider-based YouTube search discovery;
- monitored-channel ingestion;
- normalized video/channel/comment/transcript storage;
- historical statistics snapshots;
- semantic topic clustering;
- emerging trend scoring;
- comment-demand mining;
- channel-fit scoring;
- signal feed;
- signal detail page with evidence;
- content opportunity generation;
- save/dismiss/brief workflow;
- published outcome tracking;
- provider-health admin view;
- ingestion replay and manual backfill;
- demo mode with deterministic synthetic data;
- email, Slack, or Telegram digest as an optional delivery layer.

## 4.2 Explicitly out of scope

- TikTok and Instagram;
- full social listening;
- thumbnail generation;
- script generation beyond a concise evidence-backed brief;
- automatic video publishing;
- enterprise SSO;
- complex billing and entitlements;
- white-label reports;
- data resale;
- global historical YouTube indexing;
- downloading and storing full video files;
- computer-vision analysis of every video;
- predicting exact future view counts;
- end-user provider configuration;
- public API for customers;
- mobile apps.

---

# 5. Data strategy: scraping-first, provider-agnostic

## 5.1 Source strategy

The MVP uses a hybrid source hierarchy:

```text
Discovery:
third-party SERP/scraping provider first

Canonical metadata and repeated statistics:
official YouTube API when cheap and available
third-party provider fallback

Comments:
official API or third-party provider, whichever is more reliable for the job

Transcripts:
transcript provider first
scraping provider fallback
optional direct adapter fallback

Historical backfill:
dataset provider or scraping provider
```

Candidate providers include, but are not limited to:

- DataForSEO;
- SerpApi;
- Bright Data;
- Apify actors;
- Supadata;
- official YouTube Data API;
- a direct transcript adapter isolated behind the provider interface.

Provider names are configuration, not domain concepts. The application must work when any one provider is replaced.

## 5.2 Why provider abstraction is mandatory

Providers differ in:

- result freshness;
- geographic localization;
- output fields;
- comment completeness;
- transcript availability;
- pricing model;
- latency;
- rate limits;
- reliability;
- maintenance quality.

The product must be able to:

- route by capability;
- fall back on failure;
- compare results;
- replay raw payloads;
- migrate providers;
- attribute cost;
- disable an unhealthy provider without redeploying.

## 5.3 Source precedence

Default precedence by field:

| Field | Preferred source | Fallback |
|---|---|---|
| video ID | any discovery provider | monitored channel feed |
| canonical URL | derived from video ID | provider value |
| title | official API | newest provider payload |
| description | official API | scraping provider |
| published timestamp | official API | scraping provider |
| channel ID | official API | scraping provider |
| channel title | official API | scraping provider |
| duration | official API | scraping provider |
| live view count | official API | scraping provider |
| like count | official API | scraping provider |
| comment count | official API | scraping provider |
| search rank | discovery provider | none |
| transcript | transcript provider | scraping/direct adapter |
| comments | official API or scraping provider | secondary comment provider |
| thumbnail URL | official API | provider payload |

The precedence table must be configurable.

## 5.4 Provenance requirements

Every normalized value must be attributable to a provider fetch.

Minimum provenance fields:

```json
{
  "entity_type": "video",
  "entity_id": "youtube:abc123",
  "field_name": "view_count",
  "value": 184300,
  "provider": "youtube_official",
  "provider_endpoint": "videos.list",
  "provider_fetch_id": "uuid",
  "observed_at": "2026-07-26T18:00:00Z",
  "normalized_at": "2026-07-26T18:00:02Z",
  "confidence": 1.0
}
```

Do not show provenance metadata in every default user view, but make it inspectable in the admin/evidence interface.

## 5.5 Raw payload retention

Store every successful provider response before normalization.

Requirements:

- compressed JSON or provider-native text;
- immutable content hash;
- provider name and endpoint;
- request fingerprint;
- fetched timestamp;
- HTTP status or provider status;
- cost estimate;
- retention flag;
- parse version;
- normalized entity IDs.

Raw payloads enable:

- debugging parser changes;
- replaying without paying the provider again;
- comparing providers;
- recovering omitted fields;
- auditing evidence;
- backfilling new features.

Default retention for MVP: 90 days for ordinary payloads, indefinite for payloads that support a saved signal or published outcome.

---

# 6. Provider interfaces

Implement typed interfaces in the domain layer.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class DiscoveryQuery:
    query: str
    country: str = "US"
    language: str = "en"
    published_after: datetime | None = None
    max_results: int = 100
    sort: str = "relevance"


@dataclass(frozen=True)
class DiscoveredVideo:
    video_id: str
    title: str | None
    channel_id: str | None
    channel_title: str | None
    published_at: datetime | None
    position: int | None
    query: str
    raw_ref: str


class DiscoveryProvider(Protocol):
    name: str

    async def search(self, query: DiscoveryQuery) -> Sequence[DiscoveredVideo]: ...


class VideoMetadataProvider(Protocol):
    name: str

    async def fetch_videos(self, video_ids: Sequence[str]) -> Sequence["VideoMetadata"]: ...


class ChannelProvider(Protocol):
    name: str

    async def fetch_channels(self, channel_ids: Sequence[str]) -> Sequence["ChannelMetadata"]: ...

    async def list_recent_uploads(
        self,
        channel_id: str,
        published_after: datetime | None,
        limit: int,
    ) -> Sequence[DiscoveredVideo]: ...


class CommentProvider(Protocol):
    name: str

    async def fetch_comments(
        self,
        video_id: str,
        order: str,
        limit: int,
        include_replies: bool,
    ) -> Sequence["CommentRecord"]: ...


class TranscriptProvider(Protocol):
    name: str

    async def fetch_transcript(
        self,
        video_id: str,
        preferred_languages: Sequence[str],
        allow_generated: bool,
    ) -> "TranscriptResult": ...
```

## 6.1 Provider router

Implement a capability-based router:

```python
class ProviderRouter:
    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredVideo]: ...

    async def enrich_videos(self, video_ids: list[str]) -> list[VideoMetadata]: ...

    async def comments(self, video_id: str, policy: CommentFetchPolicy) -> list[CommentRecord]: ...

    async def transcript(
        self, video_id: str, policy: TranscriptFetchPolicy
    ) -> TranscriptResult: ...
```

Routing factors:

- capability;
- provider health;
- recent error rate;
- latency;
- marginal cost;
- configured priority;
- freshness requirement;
- requested country/language;
- remaining daily budget.

## 6.2 Failover rules

For each job:

1. try preferred provider;
2. retry transient errors with exponential backoff and jitter;
3. if circuit is open or retry budget exhausted, try the next provider;
4. persist each attempt;
5. never create duplicate normalized records;
6. mark partial success explicitly;
7. emit an operations event when all providers fail.

Suggested retry policy:

```text
network timeout: retry 3 times
HTTP/provider 429: obey retry-after when present, otherwise exponential backoff
5xx: retry 3 times
invalid payload: no immediate retry, mark parser/provider failure
not found: do not retry across every provider unless entity was previously known
transcript unavailable: try one fallback provider
comments disabled: terminal state for the video
```

## 6.3 Circuit breaker

Open a provider capability circuit when:

- 10 consecutive requests fail; or
- 50% of the last 20 requests fail; or
- p95 latency exceeds the configured emergency threshold for 15 minutes.

Half-open after a configurable cooldown.

Admin users must be able to manually disable a provider or capability.

---

# 7. Provider benchmark before production routing

Codex must implement a benchmark command before provider selection is considered complete.

## 7.1 Benchmark corpus

Create a versioned fixture containing:

- 100 AI/tech search queries;
- 50 known channels;
- 100 known video URLs;
- 30 videos with captions;
- 20 videos without obvious captions;
- 30 videos with large comment sections;
- 20 recent videos published within 24 hours;
- 20 niche emerging topics;
- multiple long-tail queries.

## 7.2 Benchmark metrics

For discovery:

- unique video IDs;
- overlap between providers;
- percentage published within 24 hours;
- percentage published within 7 days;
- relevant-result rate;
- duplicate rate;
- median and p95 latency;
- cost per 1,000 unique results;
- cost per relevant recent result;
- missing-field rate.

For transcripts:

- success rate;
- language accuracy;
- timestamp availability;
- text completeness;
- median latency;
- cost per successful transcript;
- native-caption versus generated status.

For comments:

- top-level comment count;
- reply completeness;
- newest-comment freshness;
- author/like/timestamp field availability;
- duplicate rate;
- median latency;
- cost per 1,000 comments.

## 7.3 Benchmark output

Produce:

- JSON results;
- CSV summary;
- Markdown decision report;
- recommended routing priorities;
- cost estimate for three ingestion volumes;
- observed caveats.

Command:

```bash
make benchmark-providers
```

or:

```bash
uv run python -m apps.worker.cli benchmark-providers --fixture fixtures/provider_benchmark.yaml
```

Do not hard-code a permanent provider choice before running this benchmark with real credentials.

---

# 8. Discovery system

Discovery should combine monitored-channel ingestion and query-based exploration.

## 8.1 Query universe

Seed the AI/tech universe with categories:

- foundation models;
- AI coding;
- agents;
- automation;
- AI video;
- AI image generation;
- consumer AI devices;
- AI productivity;
- model releases;
- developer tools;
- creator tools;
- robotics;
- major technology companies;
- AI business and monetization;
- privacy, safety, and regulation as content topics;
- comparisons and benchmarks.

Each query record includes:

```text
query text
category
priority
country
language
active flag
minimum interval
last run
next run
historical yield
cost per useful result
manual or generated source
```

## 8.2 Query expansion

Generate new queries from:

- named entities in recent titles;
- product names;
- model names and versions;
- repeated noun phrases;
- recurring comment questions;
- rising clusters;
- channel descriptions;
- co-occurring phrases;
- manual analyst input.

Generated queries require a quality score before activation.

Do not let an LLM add unlimited queries. Enforce:

- deduplication;
- category assignment;
- maximum active query count;
- historical yield pruning;
- cost budget;
- temporary expiration for event-specific queries.

## 8.3 Initial cadence

Suggested private-beta cadence:

| Query tier | Description | Frequency |
|---|---|---|
| P0 | active fast-moving launch/event | every 15 minutes |
| P1 | high-value core query | every 60 minutes |
| P2 | normal query | every 4 hours |
| P3 | exploration/long tail | daily |

Do not schedule all queries at the same minute. Add deterministic jitter.

## 8.4 Monitored channels

Maintain three channel sets:

1. global reference channels for AI/tech;
2. user-selected competitors;
3. user-owned channels.

Suggested cadence:

- top fast-moving channels: every 15 minutes;
- normal monitored channels: hourly;
- long-tail channels: every 6 hours.

The monitored-channel path should not depend on search discovery.

## 8.5 Discovery deduplication

Canonical key:

```text
youtube_video_id
```

For every discovery hit, append an occurrence record rather than creating a duplicate video.

Occurrence fields:

- provider;
- query ID;
- search rank;
- run ID;
- discovered timestamp;
- result page/token;
- localization;
- raw payload reference.

This history is useful for detecting rising search visibility.

---

# 9. Ingestion funnel and cost discipline

Do not perform expensive work on every discovered video.

## 9.1 Funnel

```text
raw discovery candidates
→ canonical deduplication
→ cheap metadata enrichment
→ language/category/relevance filter
→ repeated statistics snapshots
→ preliminary outlier and momentum features
→ topic clustering
→ candidate signal threshold
→ comments and transcripts
→ demand mining
→ final signal score
→ user-facing evidence
```

## 9.2 Suggested volume for the first vertical

Initial operating target:

```text
2,000–5,000 discovered result occurrences per day
500–1,500 unique new videos per day
200–500 retained relevant videos per day
50–150 videos receiving comments per day
20–75 videos receiving transcripts per day
3–10 user-facing signals per day
```

These are operating targets, not hard product promises.

## 9.3 Cheap pre-filter

Before comments or transcripts, compute:

- English-language probability;
- AI/tech relevance probability;
- title and description embedding similarity;
- channel vertical fit;
- publication recency;
- duplicate/reupload likelihood;
- minimum data completeness;
- channel quality floor;
- obvious spam or Shorts filter, depending on workspace preferences.

Drop or deprioritize videos that fail the filter.

## 9.4 Enrichment policy

Example policy:

```text
Metadata:
all retained videos

Statistics snapshots:
all retained recent videos for first 72 hours

Top comments:
only preliminary signal members or strong outliers

Newest comments:
only topics with active audience-demand analysis

Transcript native captions:
only videos in promising clusters

Generated transcript:
only top evidence videos when native transcript is unavailable
```

## 9.5 Budget controller

Implement daily and monthly budgets by provider and capability.

Budget actions:

- warn at 70%;
- reduce low-priority query frequency at 85%;
- stop P3 discovery at 90%;
- stop generated transcripts at 92%;
- stop non-critical comments at 95%;
- preserve P0/P1 discovery and statistics snapshots until 100%;
- hard stop provider spending at configured limit.

Every provider call must emit an estimated or actual cost record.

---

# 10. Snapshot strategy

Historical snapshots are a core asset.

## 10.1 Video snapshot schedule

For a newly discovered video, schedule snapshots approximately at:

```text
immediately
+30 minutes
+1 hour
+3 hours
+6 hours
+12 hours
+24 hours
+48 hours
+72 hours
+7 days
+14 days
+30 days
```

Use availability-aware scheduling. If the first observation is several days after publication, skip impossible early snapshots and record discovery lag.

## 10.2 Snapshot fields

- observed timestamp;
- video age in seconds;
- view count;
- like count;
- comment count;
- provider;
- source fetch ID;
- derived views per hour;
- derived likes per 1,000 views;
- derived comments per 1,000 views;
- snapshot quality;
- estimated versus direct flag.

Never overwrite a prior snapshot.

## 10.3 Channel baselines

For each channel calculate rolling baselines:

- median views at 1h, 6h, 24h, 72h, 7d;
- median views per hour;
- median engagement rates;
- upload frequency;
- duration distribution;
- topic distribution;
- format distribution;
- top-quartile and top-decile performance.

Use robust statistics. Avoid simple averages when outliers dominate.

---

# 11. Comments and audience-demand mining

## 11.1 Fetch policy

For promising videos, fetch two samples:

```text
top comments: 100–300
newest comments: 100–300
replies: only for the most discussed or demand-rich threads
```

Deduplicate by provider comment ID when available, otherwise by normalized content hash plus timestamp bucket.

## 11.2 Minimal stored fields

- provider comment ID;
- video ID;
- parent ID;
- text;
- published timestamp;
- updated timestamp if available;
- like count;
- reply count;
- top-level or reply;
- provider;
- raw payload reference;
- language;
- normalized hash.

Store author identifiers only when operationally required. They are not part of the product value.

## 11.3 Demand taxonomy

Classify comments into:

- explicit question;
- request for explanation;
- request for tutorial;
- comparison request;
- test or proof request;
- skepticism;
- objection;
- correction;
- missing use case;
- regional or audience-specific request;
- pricing request;
- privacy/safety concern;
- request for update;
- emotional reaction;
- generic praise;
- generic criticism;
- spam or irrelevant.

## 11.4 Demand clusters

Cluster semantically similar demand comments across multiple videos.

A strong unmet-demand cluster should have:

- repeated semantic intent;
- multiple distinct commenters;
- multiple distinct videos;
- preferably multiple channels;
- recency;
- limited existing content coverage;
- enough evidence snippets for human review.

## 11.5 Comment evidence rules

Customer-facing evidence may display short snippets with a direct link to the original video.

Never generate a quote that is not stored verbatim.

When comments are summarized, expose:

- comment count in cluster;
- distinct videos;
- distinct channels;
- date range;
- representative snippets;
- model confidence;
- known sampling limitations.

---

# 12. Transcript strategy

Transcripts are enrichment, not a blocking dependency.

## 12.1 Fetch order

1. native transcript from preferred transcript provider;
2. native transcript from fallback provider;
3. generated transcription only if the video is high-value evidence;
4. direct transcript adapter only if configured and isolated;
5. otherwise continue with title, description, comments, and metadata.

## 12.2 Transcript storage

Store:

- video ID;
- language;
- transcript type: native, auto-caption, generated, unknown;
- provider;
- fetched timestamp;
- full normalized text;
- timed segments when available;
- content hash;
- raw payload reference;
- quality score;
- generation cost;
- model name if generated.

## 12.3 Transcript processing

Extract:

- entities;
- key claims;
- products and model names;
- use cases;
- comparisons;
- narrative angle;
- unanswered questions;
- topic embedding;
- content format;
- evidence segments.

Do not expose entire third-party transcripts to users. Use short evidence segments and summaries.

---

# 13. Topic clustering

## 13.1 Topic representation

Construct a video representation from weighted components:

```text
title embedding: high weight
description embedding: medium weight
transcript summary embedding: medium/high when available
named entities: high weight
comment-demand embedding: separate feature
channel category: low/medium weight
```

Store embeddings with explicit version and model name.

## 13.2 Online clustering

For MVP use a practical hybrid:

1. normalize entities and product names;
2. use embedding nearest-neighbor retrieval;
3. apply temporal constraints;
4. assign to an existing topic when similarity and entity overlap pass thresholds;
5. otherwise create a candidate topic;
6. periodically merge near-duplicate topics;
7. allow admin merge/split/rename.

Do not build a complex deep-learning clustering service before the heuristic pipeline works.

## 13.3 Topic identity

A topic is not merely a keyword.

Examples:

- “Claude Code autonomous workflows”;
- “AI browser agents buying products”;
- “local video generation on consumer GPUs”;
- “AI wearable replacing a phone.”

Store:

- canonical label;
- aliases;
- key entities;
- semantic centroid;
- first observed timestamp;
- first confirmed timestamp;
- current lifecycle stage;
- active/merged/archived status;
- parent or adjacent topic relationships.

---

# 14. Trend features and scoring

All user-facing scores must expose components.

## 14.1 Video features

- age-normalized views;
- views per hour;
- change in views per hour;
- channel-relative outlier ratio;
- engagement velocity;
- search rank trajectory;
- publication recency;
- channel size;
- channel independence;
- transcript/title novelty;
- comment-demand intensity.

## 14.2 Topic features

- new videos in 6h, 24h, 72h, and 7d;
- acceleration of new video count;
- distinct channels;
- distinct creator communities;
- median channel size;
- proportion of small versus large channels;
- aggregate view velocity;
- median outlier ratio;
- top outlier ratio;
- search visibility growth;
- demand-cluster count;
- unresolved-demand density;
- content-angle diversity;
- saturation;
- fragility;
- source/provider coverage.

## 14.3 Preliminary Early Signal Score

Use a transparent weighted heuristic first:

```text
EarlySignalScore =
    0.22 * momentum
  + 0.16 * creator_diversity
  + 0.16 * outlier_strength
  + 0.15 * audience_demand
  + 0.12 * novelty
  + 0.10 * cross_community_spread
  + 0.09 * search_visibility_growth
  - 0.14 * saturation_penalty
  - 0.10 * fragility_penalty
```

Normalize each component to 0–100.

The coefficients are initial hypotheses and must be configurable.

## 14.4 Momentum

Momentum should combine:

- current new-video rate;
- acceleration versus previous window;
- aggregate view velocity;
- change in search appearance;
- recency-weighted evidence.

One large video must not dominate the score.

## 14.5 Creator diversity

Reward:

- multiple distinct channels;
- low ownership overlap;
- different channel sizes;
- different creator subcommunities;
- independent publication timing.

Penalize:

- repost networks;
- many clips from one source;
- duplicate channels;
- one company launching coordinated content.

## 14.6 Outlier strength

For video `v` on channel `c` at age `t`:

```text
outlier_ratio(v) = observed_views(v, t) / expected_views(c, t)
```

Use log transforms and robust caps.

## 14.7 Audience demand

Reward:

- repeated questions;
- requests across multiple videos;
- cross-channel demand;
- recent demand;
- demand not directly answered by existing videos;
- meaningful engagement on demand comments.

## 14.8 Novelty

Measure distance from recently saturated topics while preserving entity continuity.

A new product version may be novel even when the broad category is old.

## 14.9 Saturation penalty

Increase when:

- many large channels already published;
- total recent video count is high;
- title/angle diversity collapses;
- search results are dominated by established channels;
- upload acceleration has peaked;
- comment questions become repetitive and already answered.

## 14.10 Fragility penalty

Increase when:

- one video contributes most momentum;
- one channel contributes most evidence;
- the trend exists only in one provider's search result;
- evidence is stale;
- metrics are incomplete;
- channels are coordinated or duplicated;
- the cluster is semantically incoherent.

## 14.11 Lifecycle stages

### Seed

- weak but credible multi-source evidence;
- several small creators or one small community;
- high novelty;
- low saturation;
- low/medium confidence.

### Emerging

- accelerating video creation;
- several independent channels;
- growing view velocity;
- audience questions appearing;
- large channels mostly absent.

### Breakout

- strong acceleration;
- medium and some large channels joining;
- high confidence;
- still actionable for fast creators.

### Mass Market

- widespread coverage;
- large channels involved;
- high total reach;
- opportunity depends on differentiation.

### Saturated

- many similar videos;
- diminishing novelty;
- declining marginal performance;
- weak generic opportunity.

### Declining

- falling upload rate;
- falling view velocity;
- little new demand;
- only retrospective or contrarian angles remain.

---

# 15. Channel fit

A global signal is not automatically useful for every channel.

## 15.1 Inputs

- channel topic history;
- audience and geography when available;
- video format;
- normal duration;
- upload speed;
- historical outlier topics;
- title style;
- production capability;
- creator expertise;
- user-selected exclusions;
- user-selected strategic goals.

## 15.2 Fit components

```text
ChannelFit =
    topical_relevance
  + audience_overlap
  + format_compatibility
  + authority_or_credibility
  + production_feasibility
  + historical_performance_similarity
  + timing_feasibility
  - cannibalization_penalty
  - brand_risk_penalty
```

For MVP, normalize and weight heuristically.

## 15.3 Opportunity window

Estimate:

- earliest useful publish date;
- expected breakout window;
- expected saturation window;
- production-time fit;
- confidence.

Customer copy must use ranges, not false precision.

Example:

```text
Best publishing window: 4–8 days
Confidence: Medium
Reason: topic is spreading across 11 independent channels, but two large channels entered in the last 24 hours.
```

---

# 16. User experience

## 16.1 Main navigation

- Signals
- Watchlists
- Briefs
- Outcomes
- Settings

Admin-only:

- Ingestion
- Providers
- Queries
- Topics
- Operations

## 16.2 Signal feed

Use an evidence-dense list, not a grid of decorative KPI cards.

Each signal row/card should show:

- topic label;
- lifecycle stage;
- Early Signal Score;
- workspace Channel Fit;
- opportunity-window range;
- 24h/72h momentum summary;
- number of independent channels;
- number of evidence videos;
- strongest unmet-demand cluster;
- a small timeline/sparkline;
- actions: save, dismiss, open, create brief.

Filters:

- lifecycle stage;
- score;
- channel fit;
- category;
- publication window;
- opportunity window;
- saved/dismissed/new;
- confidence.

## 16.3 Signal detail page

Sections:

1. concise thesis;
2. why this is emerging;
3. lifecycle timeline;
4. score component breakdown;
5. evidence videos;
6. channel diffusion view;
7. audience-demand clusters;
8. saturation analysis;
9. fit for the selected channel;
10. recommended content angles;
11. content brief action;
12. provenance and data freshness drawer.

## 16.4 Evidence video table

Columns:

- thumbnail;
- title with YouTube link;
- channel;
- channel size when available;
- published age;
- views;
- view velocity;
- outlier ratio;
- role in signal;
- provider freshness;
- transcript status;
- comment sample status.

## 16.5 Content opportunity

Generate 3–5 differentiated angles, each with:

- angle title;
- audience promise;
- why now;
- evidence;
- unanswered question addressed;
- recommended format;
- expected production effort;
- timing risk;
- three title directions;
- what not to repeat from existing coverage.

Do not generate a full script by default.

## 16.6 Feedback actions

Save reasons:

- strong fit;
- early enough;
- useful audience gap;
- already planning this;
- send to team;
- other.

Dismiss reasons:

- irrelevant;
- too late;
- too early/weak;
- cannot produce quickly enough;
- already covered;
- evidence is wrong;
- not credible for channel;
- topic fatigue;
- other.

Feedback must feed evaluation and ranking.

---

# 17. System architecture

## 17.1 Recommended stack

### Web

- Next.js with TypeScript;
- React;
- Tailwind CSS;
- shadcn/ui where useful, without generic card overload;
- TanStack Query;
- Recharts or lightweight SVG charts;
- Clerk, Auth.js, or Supabase Auth.

### API and workers

- Python 3.12;
- FastAPI;
- Pydantic v2;
- SQLAlchemy 2;
- Alembic;
- `httpx`;
- `tenacity` or equivalent retry library;
- Celery, Dramatiq, Arq, or Temporal-style managed jobs;
- Redis for queues, locks, and short-lived caching.

### Data

- PostgreSQL;
- pgvector;
- object storage for raw payloads and exports;
- Redis;
- optional ClickHouse only after PostgreSQL becomes a measured bottleneck.

### AI

- provider abstraction for LLMs and embeddings;
- structured outputs;
- prompt/model versioning;
- deterministic non-LLM scoring;
- batch embeddings;
- inexpensive model for classification;
- stronger model only for final synthesis when needed.

## 17.2 Deployment

MVP-friendly options:

- Vercel for web;
- Render, Railway, Fly.io, or AWS for API/workers;
- Supabase, Neon, or managed PostgreSQL;
- S3-compatible object storage;
- managed Redis.

Keep local Docker Compose fully functional.

## 17.3 Service boundaries

```text
apps/web
apps/api
apps/worker
packages/domain
packages/provider_sdk
packages/scoring
packages/prompts
packages/contracts
packages/observability
```

The provider adapters belong outside the product domain.

---

# 18. Repository structure

```text
/
├── AGENTS.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── product.md
│   ├── data-provenance.md
│   ├── provider-benchmark.md
│   ├── operations.md
│   └── decisions/
├── apps/
│   ├── web/
│   ├── api/
│   └── worker/
├── packages/
│   ├── domain/
│   ├── contracts/
│   ├── provider_sdk/
│   │   ├── base/
│   │   ├── router/
│   │   ├── youtube_official/
│   │   ├── dataforseo/
│   │   ├── serpapi/
│   │   ├── brightdata/
│   │   ├── apify/
│   │   ├── supadata/
│   │   └── direct_transcript/
│   ├── scoring/
│   ├── clustering/
│   ├── prompts/
│   ├── observability/
│   └── test_fixtures/
├── migrations/
├── scripts/
├── fixtures/
│   ├── demo/
│   └── provider_benchmark/
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    ├── replay/
    └── e2e/
```

---

# 19. Data model

Use UUID primary keys internally and preserve canonical external IDs.

## 19.1 Workspaces

### `users`

- `id`
- `email`
- `name`
- `created_at`

### `workspaces`

- `id`
- `name`
- `slug`
- `plan`
- `timezone`
- `created_at`

### `workspace_members`

- `workspace_id`
- `user_id`
- `role`

## 19.2 Channels

### `youtube_channels`

- `id`
- `youtube_channel_id`
- `canonical_url`
- `title`
- `description`
- `country`
- `default_language`
- `subscriber_count`
- `video_count`
- `view_count`
- `published_at`
- `last_observed_at`
- `created_at`
- `updated_at`

### `workspace_channels`

- `workspace_id`
- `youtube_channel_id`
- `relationship`: owned, competitor, reference
- `priority`
- `active`

### `channel_baselines`

- `channel_id`
- `window`
- `metric_name`
- `metric_value`
- `sample_size`
- `calculated_at`
- `version`

## 19.3 Videos

### `youtube_videos`

- `id`
- `youtube_video_id`
- `channel_id`
- `canonical_url`
- `title`
- `description`
- `published_at`
- `duration_seconds`
- `default_language`
- `category_id`
- `is_short`
- `is_live`
- `thumbnail_url`
- `first_discovered_at`
- `last_observed_at`
- `created_at`
- `updated_at`

### `video_discovery_occurrences`

- `id`
- `video_id`
- `query_id`
- `provider_fetch_id`
- `position`
- `country`
- `language`
- `discovered_at`

### `video_snapshots`

- `id`
- `video_id`
- `observed_at`
- `video_age_seconds`
- `view_count`
- `like_count`
- `comment_count`
- `views_per_hour`
- `snapshot_quality`
- `provider_fetch_id`

### `video_features`

- `video_id`
- `feature_version`
- `language_probability`
- `vertical_relevance`
- `outlier_ratio`
- `view_velocity`
- `velocity_acceleration`
- `engagement_rate`
- `novelty_score`
- `spam_probability`
- `calculated_at`

## 19.4 Queries

### `discovery_queries`

- `id`
- `query`
- `category`
- `priority`
- `country`
- `language`
- `active`
- `source`: manual, generated, entity, comment
- `minimum_interval_seconds`
- `expires_at`
- `last_run_at`
- `next_run_at`
- `historical_yield`
- `cost_per_retained_video`

### `discovery_runs`

- `id`
- `query_id`
- `provider`
- `started_at`
- `completed_at`
- `status`
- `result_count`
- `unique_video_count`
- `retained_video_count`
- `estimated_cost`
- `error_code`

## 19.5 Comments

### `youtube_comments`

- `id`
- `provider_comment_id`
- `video_id`
- `parent_comment_id`
- `text`
- `published_at`
- `like_count`
- `reply_count`
- `is_reply`
- `language`
- `normalized_hash`
- `provider_fetch_id`
- `created_at`

### `comment_features`

- `comment_id`
- `taxonomy`
- `demand_probability`
- `spam_probability`
- `sentiment`
- `embedding`
- `model_version`

### `demand_clusters`

- `id`
- `topic_id`
- `label`
- `summary`
- `taxonomy`
- `comment_count`
- `distinct_video_count`
- `distinct_channel_count`
- `demand_score`
- `first_observed_at`
- `last_observed_at`
- `model_version`

### `demand_cluster_comments`

- `demand_cluster_id`
- `comment_id`
- `membership_score`
- `is_representative`

## 19.6 Transcripts

### `video_transcripts`

- `id`
- `video_id`
- `language`
- `transcript_type`
- `provider`
- `provider_fetch_id`
- `full_text`
- `content_hash`
- `quality_score`
- `generated_cost`
- `created_at`

### `transcript_segments`

- `id`
- `transcript_id`
- `start_seconds`
- `end_seconds`
- `text`
- `embedding`

## 19.7 Topics and signals

### `topics`

- `id`
- `canonical_label`
- `aliases_json`
- `entities_json`
- `centroid_embedding`
- `first_observed_at`
- `first_confirmed_at`
- `lifecycle_stage`
- `status`
- `merged_into_topic_id`
- `clustering_version`

### `topic_video_memberships`

- `topic_id`
- `video_id`
- `membership_score`
- `assignment_method`
- `assigned_at`

### `topic_snapshots`

- `id`
- `topic_id`
- `observed_at`
- `video_count_24h`
- `video_count_72h`
- `distinct_channels_72h`
- `aggregate_view_velocity`
- `median_outlier_ratio`
- `large_channel_count`
- `demand_score`
- `saturation_score`
- `fragility_score`
- `component_json`

### `signals`

- `id`
- `topic_id`
- `status`
- `lifecycle_stage`
- `score`
- `confidence`
- `opportunity_start`
- `opportunity_end`
- `thesis`
- `component_json`
- `evidence_version`
- `generated_at`
- `expires_at`

### `workspace_signal_scores`

- `workspace_id`
- `signal_id`
- `channel_id`
- `channel_fit_score`
- `fit_component_json`
- `recommended_angle_json`
- `calculated_at`

## 19.8 Outcomes

### `signal_actions`

- `id`
- `workspace_id`
- `signal_id`
- `user_id`
- `action`
- `reason`
- `created_at`

### `content_briefs`

- `id`
- `workspace_id`
- `signal_id`
- `channel_id`
- `status`
- `title`
- `brief_json`
- `created_at`
- `updated_at`

### `published_outcomes`

- `id`
- `workspace_id`
- `signal_id`
- `content_brief_id`
- `youtube_video_id`
- `published_at`
- `baseline_definition`
- `performance_json`
- `success_status`
- `user_notes`
- `created_at`

## 19.9 Provider operations

### `provider_fetches`

- `id`
- `provider`
- `capability`
- `endpoint`
- `request_fingerprint`
- `started_at`
- `completed_at`
- `status`
- `http_status`
- `attempt_number`
- `latency_ms`
- `estimated_cost`
- `actual_cost`
- `raw_payload_uri`
- `raw_payload_hash`
- `parser_version`
- `error_code`
- `error_message`

### `field_provenance`

- `id`
- `entity_type`
- `entity_id`
- `field_name`
- `provider_fetch_id`
- `observed_at`
- `confidence`
- `value_hash`

### `provider_health`

- `provider`
- `capability`
- `window_started_at`
- `request_count`
- `success_count`
- `error_count`
- `p50_latency_ms`
- `p95_latency_ms`
- `estimated_cost`
- `circuit_state`
- `updated_at`

### `provider_budgets`

- `provider`
- `capability`
- `daily_limit_usd`
- `monthly_limit_usd`
- `spent_today_usd`
- `spent_month_usd`
- `updated_at`

### `raw_payload_links`

- `provider_fetch_id`
- `entity_type`
- `entity_id`

---

# 20. API design

Use `/api/v1` and typed request/response contracts.

## 20.1 Workspace

```text
POST   /api/v1/workspaces
GET    /api/v1/workspaces/{workspace_id}
POST   /api/v1/workspaces/{workspace_id}/channels
GET    /api/v1/workspaces/{workspace_id}/channels
PATCH  /api/v1/workspaces/{workspace_id}/channels/{channel_id}
```

## 20.2 Signals

```text
GET    /api/v1/workspaces/{workspace_id}/signals
GET    /api/v1/workspaces/{workspace_id}/signals/{signal_id}
POST   /api/v1/workspaces/{workspace_id}/signals/{signal_id}/actions
POST   /api/v1/workspaces/{workspace_id}/signals/{signal_id}/briefs
```

## 20.3 Briefs and outcomes

```text
GET    /api/v1/workspaces/{workspace_id}/briefs
GET    /api/v1/workspaces/{workspace_id}/briefs/{brief_id}
PATCH  /api/v1/workspaces/{workspace_id}/briefs/{brief_id}
POST   /api/v1/workspaces/{workspace_id}/outcomes
PATCH  /api/v1/workspaces/{workspace_id}/outcomes/{outcome_id}
```

## 20.4 Admin ingestion

```text
GET    /api/v1/admin/providers
PATCH  /api/v1/admin/providers/{provider}/{capability}
GET    /api/v1/admin/provider-fetches
GET    /api/v1/admin/provider-fetches/{fetch_id}
POST   /api/v1/admin/provider-fetches/{fetch_id}/replay
GET    /api/v1/admin/discovery-queries
POST   /api/v1/admin/discovery-queries
PATCH  /api/v1/admin/discovery-queries/{query_id}
POST   /api/v1/admin/discovery/run
POST   /api/v1/admin/channels/{channel_id}/backfill
POST   /api/v1/admin/videos/{video_id}/enrich
POST   /api/v1/admin/topics/{topic_id}/merge
POST   /api/v1/admin/topics/{topic_id}/split
```

## 20.5 Evidence contract

Signal responses must include stable evidence references:

```json
{
  "signal_id": "uuid",
  "topic": {"label": "...", "stage": "emerging"},
  "score": 78.4,
  "score_components": {},
  "evidence_videos": [],
  "demand_clusters": [],
  "timeline": [],
  "data_freshness": {
    "last_video_snapshot_at": "...",
    "last_comment_fetch_at": "...",
    "last_discovery_at": "..."
  }
}
```

---

# 21. Background jobs

Required jobs:

```text
schedule_discovery_queries
run_discovery_query
ingest_monitored_channel
normalize_provider_payload
enrich_video_metadata
schedule_video_snapshots
fetch_video_snapshot
calculate_video_features
assign_video_to_topic
rebuild_topic
calculate_topic_features
select_comment_candidates
fetch_comments
classify_comments
cluster_demand
select_transcript_candidates
fetch_transcript
process_transcript
generate_or_update_signal
calculate_workspace_fit
generate_content_opportunities
send_digest
recalculate_channel_baseline
link_published_outcome
refresh_outcome_metrics
aggregate_provider_health
reconcile_provider_costs
prune_raw_payloads
```

## 21.1 Idempotency

Every job must have an idempotency key.

Examples:

```text
discovery:{provider}:{query_id}:{time_bucket}
video_snapshot:{video_id}:{scheduled_age_bucket}
comments:{provider}:{video_id}:{order}:{time_bucket}
transcript:{provider}:{video_id}:{language_policy}
topic_rebuild:{topic_id}:{feature_version}
```

## 21.2 Locks

Use distributed locks for:

- duplicate discovery runs;
- simultaneous video enrichment;
- topic rebuilds;
- provider-budget updates;
- outcome refreshes.

## 21.3 Dead-letter queue

Failed jobs that exceed retry limits must enter a reviewable dead-letter queue with:

- error summary;
- attempt history;
- provider payload references;
- replay action;
- resolution status.

---

# 22. LLM and NLP requirements

## 22.1 LLM responsibilities

Allowed:

- query expansion;
- title/description relevance classification;
- comment taxonomy;
- comment-demand summarization;
- transcript summarization;
- topic label generation;
- topic merge suggestions;
- evidence-backed signal thesis;
- content-angle generation;
- fit explanation.

Not allowed:

- inventing comments;
- inventing counts;
- inventing evidence videos;
- assigning raw trend scores without deterministic components;
- claiming predicted performance without evidence;
- silently changing topic membership.

## 22.2 Structured outputs

Every LLM call must return a versioned structured schema.

Example:

```json
{
  "schema_version": "1.0",
  "topic_label": "AI browser agents purchasing products",
  "summary": "...",
  "key_entities": ["..."],
  "audience_questions": [
    {
      "question": "...",
      "evidence_comment_ids": ["uuid"],
      "confidence": 0.84
    }
  ],
  "content_angles": [
    {
      "angle": "...",
      "evidence_video_ids": ["uuid"],
      "evidence_comment_ids": ["uuid"],
      "risk": "..."
    }
  ]
}
```

Reject outputs that reference unknown IDs.

## 22.3 Model versioning

Persist:

- provider;
- model;
- prompt version;
- schema version;
- temperature;
- input content hash;
- output;
- token usage;
- cost;
- latency;
- success/failure.

## 22.4 Embeddings

Use one embedding model per active version.

Do not silently mix vectors from different models in one index.

A migration must:

- create a new embedding version;
- backfill asynchronously;
- switch reads explicitly;
- preserve old vectors until validation.

---

# 23. Provider configuration

Example environment variables:

```bash
APP_ENV=development
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
OBJECT_STORAGE_BUCKET=...
OBJECT_STORAGE_ENDPOINT=...

YOUTUBE_API_KEY=...
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
SERPAPI_API_KEY=...
BRIGHTDATA_API_TOKEN=...
APIFY_API_TOKEN=...
SUPADATA_API_KEY=...

DISCOVERY_PROVIDER_PRIORITY=dataforseo,serpapi,brightdata,apify
METADATA_PROVIDER_PRIORITY=youtube_official,brightdata,apify
COMMENT_PROVIDER_PRIORITY=youtube_official,brightdata,apify,dataforseo
TRANSCRIPT_PROVIDER_PRIORITY=supadata,apify,direct_transcript

PROVIDER_DAILY_BUDGET_USD=50
PROVIDER_MONTHLY_BUDGET_USD=1500
GENERATED_TRANSCRIPT_DAILY_BUDGET_USD=10
RAW_PAYLOAD_RETENTION_DAYS=90
```

Do not require every provider credential. Start with whichever adapters are configured.

Validate configuration on startup and report available capabilities.

---

# 24. Admin operations interface

Build a simple internal operations surface.

## 24.1 Provider health

Show:

- provider and capability;
- enabled/disabled;
- circuit state;
- requests in last hour/day;
- success rate;
- p50/p95 latency;
- cost today/month;
- last error;
- manual disable/enable;
- routing priority.

## 24.2 Discovery operations

Show:

- active queries;
- priority;
- last and next run;
- historical yield;
- cost per retained video;
- results from latest run;
- run now;
- pause;
- edit cadence;
- expire query.

## 24.3 Ingestion explorer

Search by video ID or URL and show:

- discovery history;
- metadata sources;
- snapshots;
- comments status;
- transcript status;
- topic memberships;
- related signals;
- provider attempts;
- raw payload links;
- replay actions.

This interface is critical for fast founder debugging during the MVP.

---

# 25. Demo mode

The repository must run without external credentials.

Demo mode should include deterministic synthetic but clearly labeled data:

- 5 topics across lifecycle stages;
- 50 channels;
- 300 videos;
- historical snapshots;
- comments and demand clusters;
- transcripts for selected videos;
- one owned channel profile;
- signals with score breakdowns;
- saved/dismissed actions;
- one published outcome.

Synthetic data may be used only in demo mode and tests. Never mix it with production data.

Command:

```bash
make demo
```

Expected result:

- database seeded;
- workers optional;
- web and API start;
- login bypassed or demo user created;
- signal feed usable;
- signal detail complete;
- provider admin shows mock providers.

---

# 26. Observability

## 26.1 Metrics

Provider metrics:

- requests;
- success rate;
- error rate;
- latency;
- 429 rate;
- parser failures;
- cost;
- unique entities returned;
- retained entities;
- duplicates;
- fallback rate.

Pipeline metrics:

- discovered occurrences;
- unique videos;
- retained videos;
- snapshot lag;
- comment coverage;
- transcript coverage;
- clustering lag;
- signal generation lag;
- signals per day;
- stale signals.

Product metrics:

- signal impressions;
- signal opens;
- evidence interactions;
- saves;
- dismissals;
- briefs;
- published outcomes;
- successful outcomes.

## 26.2 Structured logs

Every ingestion log should include where relevant:

- trace ID;
- job ID;
- provider;
- capability;
- provider fetch ID;
- query ID;
- video ID;
- topic ID;
- workspace ID;
- attempt;
- latency;
- estimated cost;
- status;
- error code.

Do not log secrets or entire comment/transcript payloads.

## 26.3 Alerts

Alert on:

- all discovery providers unavailable;
- snapshot backlog over threshold;
- daily budget at 80% and 95%;
- provider failure rate over 50%;
- parser failure spike;
- no new videos discovered for a core query set;
- signal pipeline stale for more than six hours;
- raw payload storage failure.

---

# 27. Testing

## 27.1 Unit tests

- normalization per provider;
- canonical ID extraction;
- cost calculation;
- routing decisions;
- circuit breaker;
- deduplication;
- score components;
- lifecycle transitions;
- channel fit;
- comment taxonomy mapping;
- budget thresholds;
- idempotency key generation.

## 27.2 Contract tests

For each provider adapter:

- replay sanitized fixture payloads;
- validate typed normalized output;
- detect missing required fields;
- detect provider schema drift;
- verify pagination;
- verify error mapping.

Do not require live provider credentials for normal CI.

## 27.3 Integration tests

- discovery payload → canonical video;
- video → snapshots → features;
- comments → demand cluster;
- transcript → topic assignment;
- topic → signal;
- signal → workspace fit;
- provider failure → fallback;
- budget threshold → priority degradation;
- raw payload replay → same normalized result.

## 27.4 End-to-end tests

1. seed demo;
2. open signal feed;
3. filter to Emerging;
4. open signal;
5. inspect evidence;
6. save signal;
7. create brief;
8. mark published outcome;
9. verify analytics event.

Admin E2E:

1. open providers;
2. disable preferred discovery provider;
3. run discovery;
4. verify fallback provider used;
5. inspect provider fetch;
6. replay raw payload.

## 27.5 Data-science tests

- no future leakage in backtests;
- deterministic feature calculation;
- component scores in valid range;
- one-video topic receives fragility penalty;
- saturated topic cannot remain Seed;
- lifecycle transition rules are testable;
- provider duplication does not inflate creator diversity;
- coordinated channels do not count as independent when marked.

---

# 28. Backtesting

Build a time-aware backtest harness.

For evaluation time `T`, the model may only use observations at or before `T`.

## 28.1 Metrics

- precision@3 and precision@5;
- median lead time;
- false discovery rate;
- lifecycle calibration;
- saturation timing accuracy;
- signal stability;
- provider sensitivity;
- coverage by topic category;
- percentage of alerts that later cross breakout thresholds.

## 28.2 Provider sensitivity test

Run the same backtest with:

- all providers;
- discovery provider A only;
- discovery provider B only;
- no transcripts;
- no comments;
- official metadata only.

The purpose is to identify which data sources actually contribute to useful early detection.

---

# 29. Security and operational constraints

Even in aggressive MVP mode:

- keep provider keys server-side;
- encrypt secrets using deployment secret management;
- never expose raw provider credentials to the browser;
- rate-limit admin endpoints;
- protect raw payload access;
- separate production and demo data;
- sanitize logs;
- back up PostgreSQL;
- use least-privilege object-storage credentials;
- maintain a global provider kill switch;
- support deletion of a video's derived data by canonical ID.

A legal/compliance workstream must not block private-beta engineering, but data provenance and provider isolation are mandatory so sources can be replaced later.

---

# 30. Go-to-market for the first 90 days

## 30.1 Positioning

Do not lead with “AI analytics” or “YouTube scraping.”

Lead with the outcome:

> We find emerging AI/tech topics before they become obvious and show creator teams what viewers still want answered.

## 30.2 Concierge-first delivery

Before the dashboard is fully mature, send a private weekly or twice-weekly report to design partners.

Report structure:

1. top three emerging topics;
2. why each is emerging;
3. evidence videos;
4. unmet audience questions;
5. saturation/timing assessment;
6. recommended angle for the specific channel;
7. suggested decision: act, watch, or skip.

The internal product should generate most of the report, but the founder may manually edit it.

## 30.3 Design partner offer

Offer:

- free 30-day private beta;
- personalized watchlist;
- two reports per week;
- direct founder support;
- no long-term contract;
- request for structured feedback and permission to track outcomes.

Target:

- AI YouTubers;
- AI-news channels;
- coding/tool channels;
- creator agencies;
- technology newsletters with video teams.

## 30.4 Outbound workflow

For each target:

1. ingest the channel;
2. calculate recent topic profile;
3. find one current signal with high fit;
4. prepare a two-paragraph personalized observation;
5. send a concise email/DM;
6. offer the full evidence report.

Example:

```text
I noticed your strongest recent videos cluster around [topic/category].

We are tracking an early YouTube signal around [specific topic]. It has spread across [N] independent channels in [time], but large channels have not saturated it yet. The strongest unanswered viewer question is [question].

I made a short evidence report showing the source videos and a possible angle for your channel. Happy to send it over.
```

Do not send generic volume spam.

## 30.5 Pricing hypothesis

Private beta:

- free or founder-selected paid pilot.

Initial plans after evidence of usage:

- Creator: approximately $79/month;
- Team: approximately $199/month;
- Agency: starting around $499/month;
- concierge research add-on priced separately.

Treat prices as experiments.

---

# 31. Thirty-day engineering plan

## Days 1–3: repository and demo

Build:

- monorepo;
- local Docker Compose;
- schema and migrations;
- demo dataset;
- signal feed;
- signal detail;
- provider interfaces;
- mock provider;
- basic admin provider view.

Exit condition:

- product can be demonstrated end to end without credentials.

## Days 4–7: first real provider path

Build:

- one discovery provider adapter;
- one metadata provider adapter;
- raw payload storage;
- normalization;
- provenance;
- canonical deduplication;
- discovery query scheduler;
- monitored-channel ingestion;
- provider fetch explorer.

Exit condition:

- real recent AI/tech videos enter the database automatically.

## Days 8–11: snapshots and baselines

Build:

- snapshot scheduler;
- repeated metric fetch;
- video features;
- channel baselines;
- outlier ratio;
- operations metrics.

Exit condition:

- velocity and outlier calculations work on real videos.

## Days 12–15: clustering and preliminary signals

Build:

- embeddings;
- entity extraction;
- online topic assignment;
- topic snapshots;
- transparent heuristic score;
- lifecycle stage;
- admin merge/split.

Exit condition:

- internal feed shows real emerging topic candidates.

## Days 16–19: comments and demand

Build:

- comment provider;
- comment sampling;
- classification;
- semantic demand clusters;
- demand evidence UI;
- score integration.

Exit condition:

- at least one signal contains credible unmet audience demand.

## Days 20–22: transcripts

Build:

- transcript provider;
- candidate policy;
- storage and segments;
- transcript summary;
- topic enrichment;
- fallback handling.

Exit condition:

- selected high-value videos have transcript-based evidence without blocking other signals.

## Days 23–25: provider resilience

Build:

- second discovery or metadata provider;
- provider router;
- circuit breaker;
- fallback;
- budget controller;
- provider benchmark command;
- schema-drift contract tests.

Exit condition:

- disabling provider A causes provider B to complete the job.

## Days 26–28: workspace fit and briefs

Build:

- channel profile;
- channel-fit score;
- content opportunities;
- save/dismiss;
- brief creation;
- evidence-linked structured output.

Exit condition:

- a design partner can turn a real signal into a usable brief.

## Days 29–30: private beta operations

Build:

- digest;
- onboarding polish;
- analytics events;
- dead-letter queue view;
- data freshness indicators;
- production deployment;
- first customer workspace setup.

Exit condition:

- founder can onboard, monitor, and support design partners without database shell access.

---

# 32. Codex implementation slices

Codex should implement one slice at a time and keep the application runnable after every slice.

## Slice 1 — Foundation and demo

Deliver:

- `AGENTS.md`;
- architecture decision records;
- monorepo;
- local infrastructure;
- migrations;
- demo seed;
- signal feed and detail;
- mock provider;
- tests.

Do not connect paid providers yet.

## Slice 2 — Provider SDK and provenance

Deliver:

- typed provider interfaces;
- router skeleton;
- raw payload store;
- provider fetch table;
- field provenance;
- replay path;
- admin fetch explorer;
- contract fixtures.

## Slice 3 — Real discovery and metadata

Deliver:

- first configured discovery provider;
- first configured metadata provider;
- query scheduler;
- monitored channels;
- deduplication;
- normalized storage;
- cost records.

## Slice 4 — Snapshots and video intelligence

Deliver:

- snapshot scheduling;
- channel baselines;
- video velocity;
- outlier score;
- data freshness;
- operational metrics.

## Slice 5 — Topics and signals

Deliver:

- embeddings;
- entity normalization;
- topic clustering;
- topic snapshots;
- transparent scoring;
- lifecycle stages;
- real signal feed.

## Slice 6 — Comments and demand

Deliver:

- comment provider;
- comment ingestion;
- classification;
- demand clustering;
- evidence UI;
- score integration.

## Slice 7 — Transcripts

Deliver:

- transcript provider;
- candidate policy;
- segments;
- summarization;
- topic enrichment;
- graceful no-transcript behavior.

## Slice 8 — Multi-provider resilience

Deliver:

- second provider;
- routing priorities;
- circuit breaker;
- fallback;
- budgets;
- benchmark report;
- admin controls.

## Slice 9 — Channel fit and action loop

Deliver:

- channel profile;
- channel-fit score;
- content opportunity generation;
- save/dismiss;
- briefs;
- outcome linkage.

## Slice 10 — Private beta release

Deliver:

- onboarding;
- digest;
- analytics;
- production deployment;
- operations runbook;
- backup and recovery check;
- first workspace setup instructions.

---

# 33. Definition of done

The aggressive MVP is done when:

1. a founder can configure at least one third-party discovery provider;
2. the system continuously discovers current English AI/tech videos;
3. duplicate search results become one canonical video;
4. raw payloads and provenance are retained;
5. video statistics are snapshotted over time;
6. channel baselines and outlier ratios are calculated;
7. videos are clustered into coherent topics;
8. topics receive transparent component scores and lifecycle stages;
9. promising topics receive comments and transcripts according to policy;
10. unmet audience-demand clusters are visible with real evidence;
11. signals are personalized to an onboarded channel;
12. a user can save, dismiss, and create a content brief;
13. a published video can be linked to the originating signal;
14. provider failures trigger retries and fallback;
15. provider cost and health are visible;
16. the application runs in deterministic demo mode;
17. tests cover the core pipeline;
18. a private-beta deployment is operational;
19. at least one real creator can use the product without developer assistance;
20. no score or recommendation shown to the creator is based on fabricated evidence.

---

# 34. First command to give Codex

Use this exact prompt after placing this specification at the repository root:

```text
Read CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md completely.

This document is the source of truth for the aggressive MVP. Where it conflicts with any older project specification, this document wins.

Implement Slice 1 only: Foundation and demo.

Before coding:
1. Create a concise AGENTS.md from the non-negotiable rules.
2. Create docs/decisions/0001-mvp-architecture.md.
3. Create docs/decisions/0002-provider-abstraction.md.
4. Produce a short implementation plan and repository inventory.

Then build:
- the monorepo structure;
- local Docker Compose services;
- database schema and migrations needed for Slice 1;
- deterministic demo data;
- a polished signal feed;
- a complete signal detail page;
- a mock provider implementing the real provider interfaces;
- unit and end-to-end tests for the demo workflow.

Do not connect external providers yet.
Do not build billing.
Do not add TikTok, Instagram, Reddit, X, or Google Trends.
Do not add features outside Slice 1.
Do not use static screenshots as product UI.

Run formatting, linting, type checks, migrations, unit tests, and the demo end-to-end test before finishing.
Keep the application runnable at the end of the slice.
```

---

# 35. Prompt for the first real ingestion slice

After Slice 1 passes, use:

```text
Read CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md and the existing ADRs.

Implement Slice 2 and Slice 3 only:
- Provider SDK and provenance
- Real discovery and metadata

Use the provider credentials currently present in the environment. Do not require every provider.

Requirements:
1. Implement stable typed interfaces for discovery, metadata, channels, comments, and transcripts.
2. Implement raw payload storage before normalization.
3. Implement provider_fetches and field_provenance.
4. Implement deterministic request fingerprints and idempotency.
5. Implement one real discovery provider adapter.
6. Implement one real metadata provider adapter.
7. Implement query scheduling and monitored-channel ingestion.
8. Deduplicate globally by YouTube video ID.
9. Record estimated provider cost for every call.
10. Add an admin ingestion explorer and replay action.
11. Add sanitized provider fixture payloads and contract tests.
12. Preserve the working demo mode.

Do not implement comments, transcripts, topic clustering, billing, or other platforms in this slice.

Run all checks and demonstrate one real end-to-end ingestion flow from query to normalized video record.
```

---

# 36. Final product principle

The company is not building a scraper as the product.

The scraper/provider layer is disposable infrastructure used to build the real asset:

```text
longitudinal topic data
+ diffusion patterns
+ audience-demand evidence
+ creator action feedback
+ published performance outcomes
```

The MVP may use aggressive and replaceable data acquisition. The customer-facing value must remain provider-independent, evidence-backed, and focused on helping creators publish the right video before the opportunity closes.
