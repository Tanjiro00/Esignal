# EarlySignal — Implementation Plan после полного аудита

**Статус:** рабочая спецификация для Codex  
**Дата:** 29 июля 2026 года  
**Язык документа:** русский  
**Язык продукта:** английский  
**Основной источник:** `EARLYSIGNAL_FULL_PROJECT_AUDIT_PACKAGE_RU.md`

Этот документ описывает, как улучшить текущую реализацию EarlySignal без переписывания продукта с нуля.

Ключевое ограничение:

> Mandatory human review не используется как обязательный release gate.

Причина: у основателя пока нет достаточной редакционной и creator-domain экспертизы, чтобы вручную определять будущую виральность лучше автоматической системы.

Вместо обязательного human approval используются:

- conservative automated release gates;
- отдельные режимы `ACT / WATCH / HIDE`;
- shadow evaluation;
- creator feedback;
- outcome-based calibration;
- post-publication monitoring;
- автоматический downgrade/withdrawal сигнала;
- выборочная проверка data integrity и grounding, но не субъективное решение о виральности.

---

# 1. Цель следующей итерации

Текущий EarlySignal уже является рабочим private-beta продуктом:

```text
registration
→ YouTube channel onboarding
→ Today
→ Act / Watch / Skip
→ Evidence
→ Brief
→ Production
→ Result
```

Следующая итерация должна доказать и улучшить три вещи:

1. Пользователь понимает recommendation без объяснения основателя.
2. Система показывает достаточно ранние и конкретные opportunities.
3. Recommendation превращается в production decision и опубликованное видео.

Не является целью:

- добавление новых платформ;
- переписывание backend;
- создание full scriptwriter;
- увеличение числа LLM agents;
- построение enterprise-инфраструктуры;
- добавление новых score-компонентов без evaluation.

Главный продуктовый вопрос:

> Помогает ли EarlySignal профессиональному AI/tech-креатору решить, какое видео запускать следующим?

---

# 2. Главный диагноз текущей версии

## 2.1 Что уже правильно

Оставить как core:

- channel-relative baselines;
- historical video snapshots;
- topic clustering;
- stable topic identity;
- lifecycle history;
- evidence provenance;
- Act / Watch / Skip;
- content gap;
- evidence-linked brief;
- outcome association;
- deterministic scoring;
- bounded LLM enrichment;
- grounding audit;
- provider abstraction;
- demo/live separation.

## 2.2 Что сейчас недостаточно

### Product

- recommendation визуально слабее topic title;
- Today и Opportunities слишком похожи;
- content-gap alternatives часто выглядят одинаково;
- Evidence является длинным списком без аналитической группировки;
- Brief местами не соответствует заявленной длине видео;
- Results показывает слишком точный uplift без достаточного comparator context;
- onboarding не объясняет, что система поняла о канале;
- нет production-grade email delivery;
- нет creator-controlled diversity lanes.

### Data/ML

- текущий Early Signal Score описывает текущее состояние, но не является calibrated future breakout probability;
- snapshot coverage недостаточно плотный для всех candidate videos;
- transcript coverage слишком низкий для сильных content-gap claims;
- outcomes почти отсутствуют;
- нет point-in-time backtest;
- нет измеренного `ACT precision`;
- нет отдельной saturation-at-publish model;
- нет creator-specific actionability model.

### Architecture

- один worker выполняет слишком много разных типов задач;
- raw payloads находятся на локальном volume;
- LLM graph дорогой относительно числа visible signals;
- основной analyst и auditor используют одну модель;
- data model уже достаточно сложный — дальнейшее расширение нужно заморозить;
- security не полностью готова к внешним пользователям.

---

# 3. Новая модель release без mandatory review

## 3.1 Почему mandatory review не используется

Основатель не должен вручную решать:

```text
“Станет ли эта тема вирусной?”
```

если у него нет достаточной creator/editorial expertise.

Такой review может:

- добавлять субъективный шум;
- уменьшать recall;
- создавать ложную уверенность;
- замедлять выдачу;
- не давать качественных labels.

## 3.2 Что остаётся от review infrastructure

Существующие:

```text
signal_reviews
signal_review_events
review UI
split/merge actions
reason taxonomy
```

не удалять.

Использовать для:

- shadow evaluation;
- проверки data integrity;
- проверки false merge;
- проверки unsupported claims;
- разбора creator complaints;
- выборочной QA;
- будущего привлечения внешнего creator strategist.

Review не блокирует автоматический release.

## 3.3 Автоматическая release policy

Использовать три уровня:

```text
INTERNAL CANDIDATE
WATCH
ACT
```

### INTERNAL CANDIDATE

Высокий recall, пользователь не видит.

Условия:

- topic coherence прошла минимальный threshold;
- минимум 2 независимых канала;
- минимум 2 свежих video events;
- сработало минимум 2 candidate detectors;
- нет duplicate topic;
- нет критической data integrity ошибки.

### WATCH

Пользователь может увидеть в тихом режиме или отдельной секции.

Условия:

- promising momentum;
- saturation низкая;
- uncertainty высокая или evidence пока недостаточно;
- topic fit не ниже moderate;
- production window пока не закрыт;
- нет критического single-channel dependency.

WATCH не отправляет urgent notification.

### ACT

Пользователь получает recommendation.

Условия:

- strong topic coherence;
- strong or moderate-high evidence reliability;
- minimum channel diversity;
- minimum snapshot density;
- no critical concentration;
- lifecycle не Saturated/Declining;
- estimated publish window длиннее production time;
- content gap достаточно конкретный;
- channel fit не ниже conservative threshold;
- automated claim grounding прошёл;
- signal входит в top-N конкретного workspace;
- uncertainty-adjusted actionability выше ACT threshold.

## 3.4 Uncertainty-adjusted threshold

Не использовать только raw score.

Пример:

```text
conservative_actionability =
    expected_actionability
    - uncertainty_penalty
    - fragility_penalty
```

ACT создаётся только по conservative value.

## 3.5 Автоматический downgrade

Сигнал должен автоматически перейти:

```text
ACT → WATCH
WATCH → HIDE
ACT → EXPIRED
```

если:

- тема насыщается;
- новые видео перестают outperform;
- крупные каналы занимают gap;
- publish window становится короче production time;
- topic coherence ухудшается после новых данных;
- evidence provider оказался stale/invalid;
- signal был построен на merge, позже признанном ошибочным.

Пользователь получает уведомление только при meaningful change.

---

# 4. P0 — изменения интерфейса

## 4.1 Today: recommendation должна быть главным объектом

### Проблема

На текущем Today визуально крупнее:

```text
Claude Code autonomous workflows
```

чем:

```text
How do I safely let Claude Code run end-to-end on my private repos?
```

Но пользователь пришёл за идеей видео, а не за названием trend cluster.

### Требуемая иерархия

Главный заголовок:

```text
Recommended video opportunity
How do I safely let Claude Code run end-to-end on private repositories?
```

Вторичный label:

```text
Emerging topic
Claude Code autonomous workflows
```

### Acceptance criteria

- recommendation визуально крупнее trend name;
- recommendation видна в first viewport;
- topic name остаётся доступным;
- Today card можно понять без открытия detail;
- mobile показывает recommendation до scroll.

## 4.2 Sticky mobile actions

Добавить sticky bottom action bar:

```text
Create brief
Watch
Skip
```

Требования:

- safe-area support;
- не перекрывать content;
- `Create brief` primary;
- `Watch` и `Skip` secondary;
- после action показывать clear confirmation;
- поддерживать keyboard и screen reader.

## 4.3 Упростить Today card

Оставить на первом уровне:

```text
Decision
Recommended video
Why now
Why this channel
Publish by
Production estimate
Evidence strength
Main risk
Primary CTA
```

Скрыть в collapsible:

- source list;
- raw fit rationale;
- detailed risk;
- technical scores;
- transcript coverage;
- model versions.

`Check for updates` сделать вторичным.

Вместо большой кнопки:

```text
Updated 4 min ago · Refresh
```

## 4.4 Opportunities сделать библиотекой, а не копией Today

Использовать compact rows/cards:

| Opportunity | Decision | Stage | Publish by | Fit | Status |
| ----------- | -------- | ----- | ---------- | --- | ------ |

Группы:

```text
Needs decision
Watching
In production
Skipped
Expired
```

Полная decision card остаётся только на Today и Opportunity Detail.

## 4.5 Evidence: ключевые источники вместо длинного списка

Группировать:

```text
Drivers
Amplifiers
Supporting evidence
```

По умолчанию показывать 3–5 key sources.

Добавить:

- thumbnail;
- channel;
- published age;
- channel-relative outlier;
- evidence role;
- angle contribution;
- transcript availability.

Пример:

```text
Published 18h ago
3.8× above this channel’s baseline
Small developer channel
Introduced private-repository safety angle
```

Views оставить secondary metric.

## 4.6 Content gap redesign

### Primary gap

```text
Private repository safety test
```

Поля:

```text
Why it is open
Audience
Promise
What current videos cover
What current videos miss
Required proof
Production effort
Evidence strength
```

### Alternative gaps

Максимум две, действительно разные:

```text
Seven-day autonomous coding experiment
Claude Code vs Cursor under enterprise restrictions
```

Нельзя создавать alternatives, отличающиеся только формулировкой.

Показывать:

```text
Well covered
Under-covered
Unanswered audience demand
Recommended open angle
```

## 4.7 Brief: исправить structure mismatch

Разделить:

```text
Suggested opening
Full video outline
```

### Suggested opening

```text
0:00–0:20 unresolved tension
0:20–0:45 test definition
0:45–1:20 stakes and evidence
```

### Full outline

```text
0:00–1:20 Hook and setup
1:20–3:00 Permissions and safety criteria
3:00–10:00 Real workflow test
10:00–14:00 Failures and recovery
14:00–18:00 Guardrails and trade-offs
18:00–21:00 Results
21:00–23:00 Recommendation
```

Сделать brief editable.

Добавить:

```text
Working title
Owner
Target publish date
Status
Audience takeaway
Required proof checklist
Production notes
```

## 4.8 Results: объяснить comparator

Показывать:

```text
24h views
284K

Comparable median
142K

Compared with
8 similar long-form videos
Published during the last 6 months
Similar duration and topic family
```

Если comparable sample мал:

```text
Early result — not enough comparable videos for a stable uplift estimate
```

Не показывать strong percentage при sample size ниже threshold.

## 4.9 Settings redesign

Разделить на routes:

```text
Profile
Channel strategy
Production
Channels
Notifications
Connections
Security
```

Использовать:

- chips;
- autocomplete;
- suggested topics;
- toggles;
- segmented controls;
- sticky Save;
- autosave where safe;
- explicit `Saved` / `Unsaved changes`.

Password и logout перенести в Security.

## 4.10 Onboarding улучшения

После анализа канала показать:

```text
We think your channel is about:
— AI coding workflows
— developer automation
— practical product testing

Typical production:
2–4 days

Reference channels:
12
```

Buttons:

```text
Looks right
Adjust
```

Показать:

```text
Initial analysis usually takes 10–20 minutes.
We’ll email you when your first opportunity is ready.
```

Если searches ещё создаются:

```text
Focused searches are being prepared
```

---

# 5. P0 — изменения scoring и release logic

## 5.1 Разделить score на четыре независимых компонента

Создать:

```text
Breakout Potential
Saturation Risk
Evidence Reliability
Channel Actionability
```

Текущий Early Signal Score оставить:

- как explainable baseline;
- как feature source;
- как fallback;
- как ranking component.

Не называть его probability.

## 5.2 Candidate / Watch / Act cascade

### Stage A: high-recall candidate generation

Минимум два independent detector votes:

```text
burst detector
change-point detector
unique-channel acceleration
outlier persistence
search visibility growth
```

Candidate layer пользователь не видит.

### Stage B: Watch

Условия:

- promising breakout potential;
- low saturation;
- acceptable coherence;
- data uncertainty не критична;
- channel fit хотя бы Moderate.

### Stage C: Act

Условия:

- strong conservative actionability;
- minimum snapshot density;
- minimum channel diversity;
- no single-source dependency;
- open content gap;
- feasible publish window;
- grounded recommendation;
- top-N per workspace.

## 5.3 Snapshot cascade

### All discovered videos

```text
metadata only
```

### Eligible videos

```text
snapshot at discovery
one follow-up snapshot
```

### Candidate topic videos

```text
+1h
+3h
+6h
```

### Strong candidate / Watch

```text
+12h
+24h
+48h
```

### Act evidence

```text
+72h
additional refresh when decision changes
```

Если видео найдено поздно:

- не имитировать historical data;
- помечать discovery lag;
- повышать uncertainty;
- ограничивать ACT eligibility.

## 5.4 Transcript policy для ACT

Для каждого потенциального ACT:

1. выбрать top 5–10 evidence videos;
2. получить transcript для drivers, если возможно;
3. вычислить transcript coverage среди key evidence;
4. проверить content-gap claims;
5. если coverage недостаточно — смягчить язык.

Нельзя писать:

```text
Nobody has covered this
```

если content анализ неполный.

Писать:

```text
This angle appears under-covered in the available evidence.
```

## 5.5 Already-covered и cannibalization

Для owned channel проверять:

- был ли похожий topic;
- насколько давно;
- какой angle использовался;
- performance прошлого видео;
- нужен ли update;
- риск cannibalization.

Output:

```text
New opportunity
Update opportunity
Follow-up opportunity
Already covered
```

## 5.6 Diversity lanes

Добавить user-controlled strategy:

```text
Safe
Balanced
Experimental
```

Topic lanes:

```text
Core niche
Adjacent niche
Wildcard
```

Today по умолчанию:

```text
1 core
1 adjacent
optional wildcard
```

если есть достаточно quality opportunities.

---

# 6. P0 — LLM architecture и cost control

## 6.1 Измерять стоимость на бизнес-артефакт

Добавить metrics:

```text
llm_cost_per_candidate
llm_cost_per_visible_signal
llm_cost_per_act
llm_cost_per_brief
llm_cost_per_published_outcome
```

## 6.2 Упростить pipeline

Целевая схема:

```text
taxonomy reconciliation
→ deterministic first

topic synthesis + content-gap synthesis
→ один bounded call, если evidence достаточно

grounding
→ deterministic citation validator
→ optional compact verifier
```

Не использовать LLM, если:

- candidate не прошёл quality gates;
- topic не войдёт в workspace top-N;
- data coverage слишком слабое;
- deterministic fallback уже достаточен.

## 6.3 Analyst и auditor

Добавить deterministic checks:

```text
evidence ref existence
claim-source scope
metric consistency
unsupported superlatives
forbidden causal language
unknown entities
content-gap support
```

LLM verifier использовать только для semantic entailment shortlist.

## 6.4 Cache discipline

Cache key должен включать:

```text
topic revision
evidence hashes
channel profile revision
model version
prompt version
output schema version
```

---

# 7. P0 — architecture и operations

## 7.1 Logical job priorities

Добавить priority queues внутри текущей системы.

### High

```text
user-facing signal refresh
decision updates
publish-window changes
outcome suggestions
```

### Medium

```text
snapshots
comments
key transcripts
topic rebuild
```

### Low

```text
historical backfill
query expansion
non-key transcripts
bulk evaluation
```

Job fields:

```text
priority
claimed_at
lease_expires_at
heartbeat_at
max_runtime
attempt_count
```

Добавить stale lease recovery.

## 7.2 Raw payload storage

Перейти с local-only volume на S3-compatible object storage.

Требования:

```text
content-addressed keys
encryption at rest
retention policy
checksum
off-host backup
restore test
```

## 7.3 Freeze schema expansion

До достижения:

```text
10 beta users
20 production decisions
10 outcomes
```

не добавлять новые domain tables без явной необходимости.

## 7.4 Operations actionability

Каждый alert должен иметь:

```text
Problem
Impact
Likely cause
Recommended action
Runbook link
```

---

# 8. P0 — security перед external beta

Обязательно:

1. CSRF protection.
2. Email verification.
3. Password reset.
4. Session revocation.
5. Workspace isolation integration tests.
6. OAuth revoke flow.
7. Data export.
8. Data deletion.
9. Privacy page.
10. Terms page.
11. External uptime monitoring.
12. Centralized error tracking.
13. Off-host encrypted backups.
14. Restore drill.
15. Secret rotation runbook.

Не требуется сейчас:

- SAML;
- enterprise SSO;
- Kubernetes;
- multi-region HA;
- complex RBAC.

---

# 9. P1 — creator workflow

## 9.1 Email digest

Production-grade email:

```text
1 opportunity needs your decision
Publishing window: 5 days
```

Digest frequency:

```text
Immediate only for strong ACT
2–3 scheduled digests per week
Watch updates only on meaningful change
```

## 9.2 Watch behavior

При Watch пользователь выбирает:

```text
More independent channels
More audience demand
A clearer gap
A product release
More evidence
```

## 9.3 Team collaboration

Минимум:

```text
share
comment
assign
approve brief
status
```

Не строить полноценный project management.

## 9.4 Packaging

Для primary opportunity:

```text
audience promise
core tension
3 distinct title strategies
3 hook directions
2–3 thumbnail directions
required proof
clickbait mismatch risk
```

Не генерировать full script.

---

# 10. P1 — PMF instrumentation

Главная метрика:

```text
signal → production started
```

События:

```text
opportunity_seen
opportunity_opened
act
watch
skip
brief_created
brief_shared
production_started
published
outcome_confirmed
```

Причины Skip:

```text
not relevant
too late
already covered
weak evidence
no clear angle
too expensive
does not fit audience
```

Причины Watch:

```text
need more evidence
too early
waiting for release
production capacity
unclear angle
```

---

# 11. P1 — evaluation без экспертного manual review

## 11.1 Creator decisions как labels

Использовать:

```text
Act
Watch
Skip
Skip reason
Brief created
Production started
Published
Outcome
```

## 11.2 Shadow evaluation

Для каждого released signal сохранять:

```text
features_at_release
decision_at_release
future lifecycle
future channel adoption
future saturation
creator action
published outcome
```

Система автоматически размечает:

```text
breakout_72h
breakout_7d
saturated_before_publish
large_channel_adoption
dead_7d
```

## 11.3 Random QA sample

Вручную проверять только:

- false merge;
- broken evidence links;
- unsupported claim;
- duplicate topic;
- UI bug.

Не оценивать вручную будущую виральность.

## 11.4 External expert later

Review infrastructure может использоваться внешним:

- creator strategist;
- YouTube producer;
- design partner;
- paid domain expert.

Но не блокирует текущий release.

---

# 12. Этапы реализации

## Slice 0 — Baseline и safety

Цель:

- зафиксировать текущие screenshots;
- экспортировать production metrics;
- зафиксировать current API contracts;
- создать feature flags;
- создать rollback plan.

Не менять behavior.

## Slice 1 — Today hierarchy и mobile actions

Реализовать:

- recommendation > trend title;
- simplified card;
- sticky mobile actions;
- secondary refresh;
- first viewport requirements.

## Slice 2 — Opportunities library

Реализовать compact library:

```text
Needs decision
Watching
In production
Skipped
Expired
```

## Slice 3 — Evidence redesign

Реализовать:

```text
Drivers
Amplifiers
Supporting
Key evidence only
Show all
Thumbnails
Outlier vs baseline
Angle contribution
```

## Slice 4 — Content gap redesign

Реализовать:

```text
Primary gap
Occupied coverage
Why it is open
Required proof
Two distinct alternatives
```

## Slice 5 — Brief correction

Реализовать:

- Suggested opening;
- Full outline;
- duration consistency;
- editable fields;
- proof checklist;
- target publish date;
- owner/status.

## Slice 6 — Results comparator

Реализовать:

- sample size;
- comparable-video methodology;
- stable/unstable estimate;
- non-causal copy;
- minimum sample threshold.

## Slice 7 — Settings и onboarding

Реализовать:

- settings routes;
- chips/autocomplete;
- save state;
- onboarding inferred profile;
- expected wait time;
- progress state.

## Slice 8 — Automated ACT / WATCH / HIDE policy

Реализовать:

```text
candidate detector votes
evidence reliability
saturation risk
channel actionability
uncertainty penalty
automatic downgrade
```

Mandatory review не включать.

## Slice 9 — Snapshot cascade и transcript policy

Реализовать selective dense tracking.

Добавить:

```text
ACT key-evidence transcript coverage
discovery lag
trajectory quality
claim-language downgrade
```

## Slice 10 — Already covered и diversity lanes

Реализовать:

```text
new
update
follow-up
already covered
core
adjacent
wildcard
```

## Slice 11 — LLM cost reduction

Реализовать:

- cost metrics;
- fewer calls;
- deterministic validators;
- stronger cache;
- compact verifier.

## Slice 12 — Job priorities и off-host storage

Реализовать:

- priority;
- leases;
- heartbeats;
- stale recovery;
- S3-compatible raw evidence;
- restore test.

## Slice 13 — Security beta readiness

Реализовать security P0 list.

## Slice 14 — Email и Watch notifications

Реализовать production email delivery и meaningful updates.

## Slice 15 — PMF instrumentation

Реализовать:

- full funnel;
- skip/watch reasons;
- shadow labels;
- evaluation report;
- cohort export.

---

# 13. Acceptance criteria private beta

## UX

- recommendation понятна без объяснения;
- mobile CTA доступен;
- onboarding объясняет inferred profile;
- brief structure соответствует duration;
- evidence показывает key sources first.

## Product

- ACT signals автоматически проходят conservative gates;
- Watch не создаёт notification spam;
- duplicate/covered opportunities минимизированы;
- publish-by учитывает production time.

## Data

- key evidence имеет достаточную snapshot density;
- content-gap language учитывает transcript coverage;
- historical features сохраняются point-in-time;
- automatic downgrade работает.

## Security

- password reset;
- email verification;
- CSRF;
- workspace isolation tests;
- off-host backup;
- privacy/terms;
- data delete/export.

---

# 14. Метрики следующего этапа

Цели для первых 5 creators:

| Метрика                                    |                         Цель |
| ------------------------------------------ | ---------------------------: |
| Opportunity understood without explanation |                         80%+ |
| Median decision time                       |                       <2 min |
| Act or Watch rate                          |                       20–40% |
| Signal → brief                             |                         15%+ |
| Signal → production                        |                         10%+ |
| Users with ≥1 production decision/month    |                         40%+ |
| Dismissed as irrelevant                    |                         <30% |
| Dismissed as too late                      |                         <20% |
| Email digest open rate                     |                         >40% |
| ACT false breakout rate                    | измерять, не обещать заранее |

Data targets:

```text
20 production decisions
10 published videos
5–10 mature outcome windows
```

---

# 15. Что не делать до появления outcomes

Не делать:

- TikTok;
- Instagram;
- generic AI chat;
- full script generation;
- thumbnail image generation;
- Kubernetes;
- distributed microservices;
- enterprise permission system;
- новые agent roles;
- новые scoring dimensions;
- public viral probability claims;
- автоматические claims о revenue uplift.

---

# 16. Первый prompt для Codex

```text
Read completely:

1. EARLYSIGNAL_FULL_PROJECT_AUDIT_PACKAGE_RU.md
2. EARLYSIGNAL_POST_AUDIT_IMPLEMENTATION_PLAN_RU.md
3. Relevant ADRs, routes, tests and current frontend components.

Implement Slice 0 only: Baseline and safety.

Important:
- Do not enable mandatory signal review.
- Do not modify the current release policy yet.
- Do not redesign UI.
- Do not change score weights.
- Do not add providers.
- Do not begin Slice 1.

Required work:
1. Capture the current desktop and mobile UI baseline.
2. Export current production/demo metrics needed for regression.
3. Document current Today, Opportunities, Evidence, Content gap, Briefs, Results, Settings and admin contracts.
4. Document current feature flags and release policy.
5. Create rollback instructions.
6. Create docs/decisions/post-audit-baseline.md.
7. Create fixtures/evaluation/post-audit-baseline.json.
8. Run format, lint, typecheck, migrations, backend tests, frontend tests, E2E and build.

Finish with:
- files changed;
- screenshots captured;
- API contracts documented;
- baseline metrics;
- test results;
- blockers for Slice 1.

Do not make product behavior changes.
```

---

# 17. Итоговая продуктовая позиция

После реализации продукт должен ощущаться так:

> EarlySignal находит растущую YouTube-возможность, показывает конкретное видео, которое канал ещё может занять, объясняет evidence и помогает быстро перейти к production.

Он не должен ощущаться как:

> сложная аналитическая система с красивыми score и большим количеством внутренних данных.

Главный следующий этап — не увеличение технической сложности, а получение:

```text
creator decision
→ production
→ publication
→ measured outcome
```

Mandatory review для этого не нужен.

Нужны:

- conservative release gates;
- честная uncertainty;
- creator feedback;
- automatic future labels;
- outcome calibration;
- быстрый и понятный UX.
