# Provider benchmark

Generated: 2026-07-27T14:27:18.208789+00:00
Mode: stored_observations
Fixture corpus: 100 discovery queries.

## Recommended priority

- **channels:** youtube_web → youtube_official
- **comments:** youtube_official → youtube_web_comments
- **discovery:** youtube_official → youtube_web
- **metadata:** youtube_official
- **transcripts:** youtube_transcript

## Metrics

| Capability | Provider | Requests | Success | p50 | p95 | Yield | Fallback |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| channels | youtube_official | 30 | 100.0% | 259 ms | 508 ms | 7.83 | 0.0% |
| channels | youtube_web | 5 | 100.0% | 168 ms | 377 ms | 22.0 | 0% |
| comments | youtube_official | 67 | 100.0% | 318 ms | 542 ms | 1.0 | 0.0% |
| comments | youtube_web_comments | 5 | 100.0% | 1830 ms | 5347 ms | 1.0 | 0% |
| discovery | youtube_official | 4 | 100.0% | 594 ms | 824 ms | 16.5 | 100.0% |
| discovery | youtube_web | 26 | 100.0% | 944 ms | 2095 ms | 9.04 | 0.0% |
| metadata | youtube_official | 36 | 100.0% | 273 ms | 754 ms | 10.47 | 0.0% |
| transcripts | youtube_transcript | 35 | 100.0% | 1087 ms | 2002 ms | 1.0 | 0% |

## Caveats

- YouTube API quota units are tracked separately from USD; current adapters report zero direct USD cost.
- Precision, transcript accuracy, and comment recall need a human-labeled gold set and are intentionally not inferred.
- Stored-observation mode reflects the last 30 days of real provider traffic; live mode adds bounded raw probes only.
