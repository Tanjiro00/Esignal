# EarlySignal — gap-анализ нового implementation plan

Статус: **рабочая карта реализации**  
Дата проверки: **7 августа 2026 года**  
Источник плана: `/Users/daniil/Downloads/earlysignal_implementation_plan.md`  
SHA-256 источника: `8d37971772c51c856af394535a77049823dc69ba74c869d7308526e170d768fe`

## 1. Назначение документа

Этот документ сопоставляет новый 12-недельный план с:

- фактическим кодом EarlySignal;
- текущей схемой данных;
- read-only состоянием production на `45.129.124.109`;
- обязательными правилами из корневой scraping-first спецификации.

Это не план переписывания продукта с нуля. Новый документ используется как
quality roadmap поверх уже работающей системы.

При конфликте действует следующий приоритет:

1. `CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md`;
2. `AGENTS.md` и текущая граница продукта;
3. настоящий gap-анализ;
4. новый `earlysignal_implementation_plan.md` как стратегическое направление.

## 2. Executive summary

EarlySignal уже реализовал большую часть продуктового и ingestion-контура,
который новый план относит к неделям 1–7 и 9–12:

- provider-agnostic YouTube discovery;
- нормализацию, дедупликацию, raw payloads и provenance;
- snapshots и channel baselines;
- deterministic topic/scoring pipeline;
- comments, demand и transcripts;
- Channel Fit, Today, Opportunities, Briefs и Results;
- onboarding, auth, workspace isolation и production deployment;
- LLM synthesis с evidence-grounding audit.

Однако центральное обещание нового плана пока не доказано:

> система не умеет воспроизводимо показать, что её рекомендации имеют
> `precision@10 >= 40%` и появляются минимум за 21 день до подтверждённого
> роста темы.

Главный P0 — не ещё один UI-срез и не увеличение числа собираемых видео, а
point-in-time backtest без data leakage, слепая разметка и честный отчёт
качества.

Критические факты production:

- `35 929` YouTube-видео;
- `138 626` snapshots;
- `35 929` видео имеют хотя бы один snapshot, но только `3 002` имеют успешно
  сохранённую плановую точку около 24 часов;
- `283` активные live topics и `34` активных live signals;
- `0` expert evaluation labels;
- `3` пользовательских signal actions;
- `1` published outcome;
- `0` сохранённых provider benchmark runs.

Следовательно, объём ingestion уже достаточен для начала строгой оценки, но
плотность ранних historical measurements и количество labels/outcomes пока
недостаточны для заявления о predictive quality.

## 3. Фактическое состояние production

Read-only проверка выполнена 7 августа 2026 года. API, PostgreSQL, Redis и
worker были запущены; readiness сообщил `database=ready`, `worker_fresh=true`,
`stale_topic_runs=0`.

### 3.1 Data asset

| Сущность                        | Количество |
| ------------------------------- | ---------: |
| YouTube channels                |      2 816 |
| YouTube videos                  |     35 929 |
| Video snapshots                 |    138 626 |
| Videos с хотя бы одним snapshot |     35 929 |
| Channel baseline rows           |     28 707 |
| Video feature rows              |     35 629 |
| Video embedding rows            |     17 544 |
| Topic snapshots                 |    806 818 |
| Topic snapshot buckets          |     31 630 |
| Topic-video memberships         |      2 545 |
| Active live topics              |        283 |
| Active live signals             |         34 |
| Workspace signal scores         |        740 |
| Comments                        |     10 119 |
| Demand clusters                 |         26 |
| Transcripts                     |        129 |
| Provider fetches                |     57 515 |
| Discovery runs                  |     16 581 |
| LLM intelligence runs           |      5 297 |

### 3.2 Реальная пригодность snapshots для backtest

Наличие любого snapshot не означает наличие честного views-at-age. Успешные
плановые snapshot jobs распределены так:

| Возраст видео | Successful | Skipped из-за позднего discovery |
| ------------- | ---------: | -------------------------------: |
| 30 минут      |        204 |                           35 320 |
| 1 час         |        416 |                           35 000 |
| 3 часа        |        846 |                           34 378 |
| 6 часов       |      1 336 |                           33 715 |
| 12 часов      |      1 987 |                           32 750 |
| 24 часа       |      3 002 |                           31 311 |
| 48 часов      |      3 876 |                           29 459 |
| 72 часа       |      4 011 |                           27 999 |
| 7 дней        |      2 745 |                           23 386 |
| 14 дней       |      1 414 |                           18 329 |
| 30 дней       |        701 |                           12 410 |

Вывод: historical search дал широкий каталог, но не может восстановить ранние
счётчики задним числом. Первый backtest обязан использовать отдельный eligible
cohort только с реально наблюдёнными point-in-time measurements. Иначе будет
look-ahead bias.

### 3.3 Learning loop

| Сущность           | Количество |
| ------------------ | ---------: |
| Evaluation labels  |          0 |
| Signal actions     |          3 |
| Published outcomes |          1 |
| Signal reviews     |         12 |
| Approved reviews   |          6 |
| Rejected reviews   |          1 |

Review history полезна как QA evidence, но не заменяет независимую blind
разметку исходов и creator outcomes.

### 3.4 Operations

Все live provider circuits на момент проверки были закрыты. Накопленная
история содержит:

- 153 failed snapshot jobs;
- 31 failed discovery runs;
- 151 failed demand runs;
- 70 failed topic runs;
- 48 failed LLM runs.

Эти значения являются cumulative, а не утверждением о текущей аварии. Для
оценки надёжности нужны error rate за окно, retry outcome и time-to-recovery,
а не только lifetime counters.

## 4. Сопоставление нового плана по фазам

Легенда:

- **готово** — capability есть в production-коде;
- **частично** — основа есть, но метод или качество не соответствуют плану;
- **нет** — capability отсутствует;
- **отложено** — противоречит текущей границе или преждевременно.

| Фаза нового плана   | Статус          | Что уже есть                                                                                                          | Главный gap                                                                                                                                               |
| ------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0. Фундамент        | Частично        | Python 3.12, FastAPI, PostgreSQL 17 image, Redis, Docker Compose, Alembic, Ruff, mypy, pytest                         | Нет CI workflow; Redis не используется worker-кодом; нет YouTube quota-unit ledger; pgvector extension не включён                                         |
| 1. Ingestion        | Готово/частично | Web-first discovery, official metadata, channel monitoring, comments, raw evidence, snapshots, baselines, idempotency | Нет строгого endpoint quota accounting; snapshot early-age coverage ограничен поздним discovery; нет доказанного dashboard/SLO по freshness и quota units |
| 2. Кластеризация    | Частично        | 64-dim hashing embeddings, entity/facet microtopics v5, stable identity, topic history, LLM naming/audit              | Нет sentence-transformer embeddings, vector index, HDBSCAN challenger и формального day-to-day Jaccard stitching benchmark                                |
| 3. Сигналы и SCORE  | Частично        | Deterministic score v3, lifecycle, velocity/outlier, diversity, demand, novelty, saturation/fragility                 | Нет formal event-vs-trend classifier, property-based tests, калиброванного vpd/views-at-age switch и outcome-calibrated thresholds                        |
| 4. Fit и выдача     | Готово/частично | ChannelProfile v2, Channel Fit v1, opportunity cards, evidence links, onboarding, briefs                              | Fit в основном эвристический/token-based; timing window не доказан historical analogs; ranking не откалиброван на outcomes                                |
| 5. Backtest         | Нет/начало      | Point-in-time evidence snapshots, evaluation labels schema, lifecycle history, export utilities                       | Нет replay harness, checkpoint manifests, blind outcome labeler, precision@10, lead-time report, train/holdout split и commit freeze workflow             |
| 6. Продукт          | Частично        | Landing, auth, onboarding, Today, Library, Briefs, Results, settings, in-app digest                                   | Нет production email delivery, public track record и достаточного pilot outcome sample; billing запрещён текущей границей                                 |
| 7. External signals | Отложено        | Provider abstraction позволяет добавить источники                                                                     | HN/Reddit/GitHub/Google Trends отсутствуют и не должны смешиваться с YouTube score до отдельной валидации                                                 |

## 5. Что нужно сохранить без переписывания

Новый план содержит упрощённую greenfield-схему. Следующие существующие части
сильнее и должны остаться:

1. `users + workspaces + workspace_members` вместо одного `users.plan`.
2. Typed provider SDK и routing decisions вместо прямых вызовов YouTube из
   domain logic.
3. Content-addressed gzip raw payload store и `field_provenance` вместо одного
   неограниченного JSONB-склада.
4. Immutable snapshot jobs с явным `skipped`, когда target age уже прошёл.
5. Versioned video features, embeddings, topics, signals и fit records.
6. Evidence-grounded LLM synthesis и отдельный Skeptic/Auditor trace.
7. Existing `/api/v1` contracts и работающий creator workflow.
8. Demo/live isolation.
9. Auth, cookie sessions, login throttling и server-side workspace checks.
10. Existing outcome association и channel-relative comparator UI.

## 6. Критические gaps

### P0.1 — Нет доказанной predictive quality

Существующий evaluation package считает отчёт по ручным labels, но:

- labels в production отсутствуют;
- нет исторического replay pipeline;
- нет `as_of_date` как сквозного execution context;
- нет контрольного списка разрешённых таблиц/полей для backtest;
- нет защиты от чтения будущих snapshots, comments, memberships и LLM output;
- нет precision@10 и lead-time-to-outcome;
- нет train/holdout checkpoint split;
- нет commit hash и dataset manifest у каждого прогона.

Это главный блокер заявления «EarlySignal находит тренды раньше».

### P0.2 — Historical coverage неоднороден

Каталог из десятков тысяч видео выглядит большим, но ранние прямые snapshots
есть только у меньшей части. Нельзя:

- использовать сегодняшний view count как будто он был известен в `t0`;
- восстанавливать 24h views из текущего значения без маркировки estimate;
- считать backfilled topic snapshots эквивалентом реально наблюдённой истории;
- смешивать discovery cohorts с разной глубиной coverage без weights/strata.

Нужны eligibility rules, coverage report и отдельная оценка по cohort/date.

### P0.3 — Метрика query precision не равна product precision

У 73 активных discovery queries production показывает `precision_score=100`
на 47 423 samples. Это operational retained-result precision текущей query
логики, а не precision тренд-прогноза и не creator acceptance. Её нельзя
показывать как доказательство качества рекомендаций.

### P0.4 — Слишком мало ground truth

Три действия и один outcome не позволяют калибровать ranking. Нужны минимум:

- 50–100 независимых topic labels для первого offline анализа;
- 6–8 historical checkpoints;
- 10–20 beta-креаторов или другой заранее зафиксированный pilot cohort;
- минимум 20 связанных публикаций для первого directional outcome analysis.

### P1.1 — Embeddings и clustering пока эвристические

Production использует:

- `local-hashing-title-entity-transcript-v2`;
- 64 измерения;
- JSON vectors;
- entity/facet clustering.

PostgreSQL запущен из pgvector image, но расширение `vector` не установлено и
vector-колонок нет. Это ограничивает semantic recall, paraphrase handling и
поиск missed merges.

Но HDBSCAN нельзя включать сразу как replacement. Сначала он должен работать
как challenger на замороженном corpus и сравниваться по:

- pairwise cluster precision/recall;
- false merge rate;
- missed merge rate;
- identity stability день-к-дню;
- доле noise;
- стоимости и latency.

### P1.2 — Worker не является реальной очередью

Redis работает, но Python-код его не использует. Один worker последовательно
poll’ит ingestion, snapshots, demand, transcripts, topics, digests и outcomes.

Риски:

- одна медленная provider operation задерживает остальные pipelines;
- нельзя безопасно масштабировать разные job classes независимо;
- нет отдельной retry/dead-letter политики на уровне очереди;
- restart повторно проходит общий startup workload;
- при росте snapshots и external sources появится contention.

Нужно принять отдельное ADR: Celery + Redis либо сохранить DB-backed jobs, но
добавить leases, независимые worker pools, retry schedules и dead-letter queue.
Просто держать неиспользуемый Redis смысла нет.

### P1.3 — Quota accounting неполон

Есть provider USD budgets, fetch cost и provider health, но нет отдельного
YouTube quota-unit ledger по дню и endpoint. `search.list` и `videos.list`
имеют принципиально разную цену, поэтому USD-only budget не обеспечивает
правильную приоритизацию snapshots против discovery.

### P1.4 — Topic history слишком объёмна

Production накопил `806 818` raw topic snapshots при `31 630` hourly buckets.
Raw history полезна для аудита, но требует:

- retention/compaction policy;
- отделения immutable source measurements от повторных no-change runs;
- backtest чтения стабильных buckets, а не случайной записи внутри часа;
- индексов и query plans для роста на месяцы.

### P1.5 — Event/trend и timing пока не доказаны

В коде нет отдельного versioned `is_event` classifier из нового плана.
Publish-by/timing строится из текущих эвристик, а не из проверенных historical
analogs конкретного lane и production delay канала.

### P2 — Product и operations

- Email digest сейчас не является подтверждённым production delivery channel.
- Public track record не реализован.
- Provider benchmark framework есть, но production runs отсутствуют.
- Нет GitHub Actions/другого CI workflow, хотя локальные quality commands есть.
- Нужны off-host backups, restore drills, external uptime и structured alerting.
- VPS на момент аудита показывал большое количество доступных OS/security
  updates; обновление нужно проводить отдельным обслуживаемым окном.

## 7. Конфликты нового плана с действующими правилами

### 7.1 Official-API-first против scraping-first

Новый план делает `search.list` центральным discovery path. Корневая
спецификация требует scraping-first и provider-agnostic routing. Решение:

- сохранить `youtube_web` первым discovery provider;
- использовать official API для canonical metadata и fallback discovery;
- учитывать quota units независимо от provider USD cost;
- запускать provider sensitivity test в backtest.

### 7.2 Billing

Новый план включает Stripe на фазе 6. Текущая граница репозитория явно запрещает
billing. Он остаётся вне implementation backlog до отдельного решения владельца.

### 7.3 External social sources

Reddit, HN, GitHub и Google Trends выходят за текущий YouTube-only scope. Их
можно исследовать позже как изолированный `pre_youtube` evidence class, но:

- они не меняют deterministic YouTube score без отдельной валидации;
- каждый visible claim должен иметь URL и stored provenance;
- Reddit discussion volume нельзя автоматически трактовать как creator demand;
- source-specific time windows и anti-spam правила обязательны.

### 7.4 Замена существующей схемы

Таблицы из нового плана являются логической моделью, а не миграционным заданием.
Existing schema богаче. Все изменения должны быть additive и backward-compatible.

## 8. Адаптированный implementation backlog

### Slice A — Backtest contract и leakage firewall

Приоритет: **P0**

1. Ввести типизированный `AsOfContext` для всех evaluation queries.
2. Зафиксировать allowlist полей и timestamp semantics.
3. Добавить immutable `backtest_runs`, `backtest_checkpoints` и dataset manifest.
4. Сохранять commit hash, migration revision, model versions и input hashes.
5. Запретить чтение evidence с timestamp после checkpoint.
6. Определить direct/estimated/backfilled eligibility flags.
7. Добавить leakage tests с намеренно вставленными future rows.

Выход: один checkpoint воспроизводится байт-в-байт и не видит будущего.

### Slice B — Historical cohort и ground truth

Приоритет: **P0**

1. Построить coverage report по target age, lane, channel size и date cohort.
2. Выбрать 6–8 checkpoints, для которых реально существует post-window.
3. Реализовать blind label flow поверх существующей `evaluation_labels`.
4. Отделить prediction snapshot от outcome evidence.
5. Зафиксировать outcome rule, например supply growth `>=3x` и median
   channel-relative lift `>=3x` после `t0`.
6. Добавить экспертные false-merge/missed-merge labels.

Выход: versioned labeled dataset, пригодный для честной оценки.

### Slice C — Backtest harness и baseline report

Приоритет: **P0**

1. Replay production pipeline с `as_of_date`.
2. Сохранять top-N predictions каждого checkpoint до открытия outcomes.
3. Считать `precision@3`, `precision@10`, recall, median lead time,
   false-positive rate, coverage и calibration.
4. Разделить train и holdout checkpoints.
5. Автоматически генерировать Markdown + JSON report.
6. Не менять score weights между commit freeze и holdout report.

Quality gate:

- `precision@10 >= 40%`;
- median/mean lead time, заранее выбранный в metric contract, `>=21 day`;
- отдельно опубликованы sample size и confidence intervals;
- нет leakage violations;
- provider sensitivity не меняет вывод радикально.

Если gate не пройден, работа возвращается к data/signals, а не к UI.

### Slice D — Semantic challenger

Приоритет: **P1 после первого baseline**

1. Включить pgvector extension отдельной проверяемой миграцией.
2. Добавить 768-dim embeddings параллельно hashing embeddings.
3. Кэшировать model/version/source hash.
4. Запустить HDBSCAN как shadow challenger.
5. Реализовать explicit day-to-day cluster stitching.
6. Сравнить с текущим microtopic v5 на frozen labeled corpus.
7. Продвигать challenger только при измеримом улучшении holdout metrics.

### Slice E — Signal, event и Fit calibration

Приоритет: **P1**

1. Формализовать views-at-age/vpd fallback по coverage.
2. Добавить versioned event-vs-trend classifier.
3. Проверить demand contribution отдельно от общего score.
4. Калибровать score thresholds только на train checkpoints.
5. Построить timing analogs по lane и creator production delay.
6. Сравнить token-based Fit с semantic/profile challenger.
7. Добавить property-based tests для score monotonicity и bounds.

### Slice F — Queue и quota reliability

Приоритет: **P1 до масштабирования pilot**

1. Ввести YouTube quota ledger: date, endpoint, units, calls, operation key.
2. Приоритизировать snapshots выше expensive search.
3. Разделить ingestion, snapshots, intelligence и notifications на job classes.
4. Реализовать leases, exponential retry и dead-letter state.
5. Поддержать минимум два worker процесса без double execution.
6. Добавить CI для format/lint/typecheck/migrate/test/e2e.

### Slice G — Pilot и track record

Приоритет: **после прохождения backtest gate**

1. Подключить 10–20 design partners.
2. Собирать reasoned Act/Watch/Skip и time-to-decision.
3. Связывать brief → publish → outcome.
4. Включить production email delivery.
5. Публиковать track record с denominators и без causal overclaim.
6. Измерять acceptance, brief-to-publish и uplift против channel baseline.

### Slice H — External pre-YouTube evidence

Приоритет: **после pilot или отдельным research experiment**

1. HN и Reddit — первые кандидаты.
2. Хранить source-specific evidence и canonical URL.
3. Создать отдельный lifecycle `pre_youtube`.
4. Не смешивать с production SCORE до offline validation.
5. Измерять, даёт ли источник дополнительный lead time, а не просто volume.

## 9. Рекомендуемый порядок на 12 недель с текущей точки

| Недели | Работа                                            | Решение на выходе                        |
| ------ | ------------------------------------------------- | ---------------------------------------- |
| 1      | Slice A: as-of contract, manifests, leakage tests | Можно ли честно воспроизвести прошлое    |
| 2–3    | Slice B: eligibility cohorts и blind labels       | Есть ли пригодный ground truth           |
| 4      | Slice C: первый baseline backtest                 | Реальное текущее качество без калибровки |
| 5–6    | Slice D/E: semantic и scoring challengers         | Что действительно улучшает metrics       |
| 7      | Train calibration, commit freeze                  | Финальная candidate policy               |
| 8      | Holdout backtest                                  | Проходит ли quality gate                 |
| 9–10   | Slice F: queue/quota/CI reliability               | Готова ли система к pilot load           |
| 11–12  | Slice G: pilot, email, track record               | Полезен ли продукт реальным creators     |

External signals не входят в критический путь этих 12 недель.

## 10. Что не нужно делать сейчас

1. Переписывать FastAPI/Next.js или существующий API.
2. Мигрировать всю систему на HDBSCAN до benchmark.
3. Менять score weights на основании нескольких красивых примеров.
4. Показывать query precision как точность прогноза.
5. Считать backfilled snapshots равными direct observations.
6. Добавлять ещё один UI-раздел до первого backtest report.
7. Включать billing до доказанной полезности.
8. Смешивать Reddit/HN volume с YouTube trend score.
9. Удалять current review/audit infrastructure: она полезна для labels, даже
   если не является mandatory moderation gate.

## 11. Definition of Done всей программы

Программа считается завершённой, когда одновременно выполняются условия:

- каждый backtest run воспроизводим и привязан к commit/dataset/model versions;
- leakage tests проходят;
- опубликован размер eligible cohort и coverage по возрастным точкам;
- есть минимум 6–8 checkpoints;
- есть blind labels и holdout split;
- опубликованы precision@k, recall, lead time и confidence intervals;
- quality gate пройден либо честно зафиксирован как провал;
- каждое visible решение разрешается до stored evidence URLs;
- Channel Fit и timing имеют отдельную оценку;
- production jobs безопасно повторяются и не дублируют данные;
- pilot outcomes сравниваются с channel baseline без causal overclaim;
- public track record показывает denominator, методику и ограничения.

## 12. Ближайший исполняемый шаг

Следующая реализация должна начинаться со **Slice A — Backtest contract и
leakage firewall**.

Первый pull-sized результат:

1. ADR с temporal semantics всех evidence tables;
2. `AsOfContext` и point-in-time repository helpers;
3. schema для backtest run/checkpoint/prediction manifest;
4. leakage fixtures и тесты;
5. CLI, который воспроизводит один checkpoint и создаёт deterministic JSON,
   пока без изменения production score и UI.

Это минимальный шаг, который превращает накопленные данные в проверяемый
product-quality asset.
