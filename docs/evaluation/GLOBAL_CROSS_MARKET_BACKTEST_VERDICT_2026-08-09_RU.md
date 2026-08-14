# EarlySignal: вердикт глобального historical backtest на 2026-08-09

## Короткий ответ

**Нет, исторический тест не подтвердил, что текущий метод заранее находит темы,
которые затем становятся виральными.**

Статус основной гипотезы остаётся **NOT VALIDATED**. Формальный holdout verdict:
`INSUFFICIENT_OUTCOME_SUPPORT`.

Это не положительный результат и не статистически сильное доказательство нулевой
precision. В holdout сформировался только один eligible topic episode, и он не
выполнил заранее замороженный future outcome.

## Что было проверено

Использован независимый [Global YouTube Trending Dataset 2022–2025](https://databank.illinois.edu/datasets/IDB-9307654)
Illinois Data Bank:

- четыре исторических Trending snapshot в день;
- 104 заявленных национальных рынка в исходном датасете;
- point-in-time `view_count`, rank, video ID, channel ID и country code;
- фактически прочитано 71 940 519 CSV-наблюдений;
- English AI/tech admission, taxonomy v6 и deterministic production score;
- никакая LLM не меняла score, rank или outcome;
- train физически сохранён и захеширован до открытия holdout.

Источник проверяет распространение темы **после первого появления в публичном
YouTube Trending**. Он не содержит полный universe обычных загрузок до Trending,
поэтому этот replay нельзя называть проверкой предсказания до любого platform
confirmation.

## Замороженный протокол

- Train: 2022-07-01 — 2024-06-30.
- Holdout: 2024-07-01 — 2025-06-30.
- Недельные checkpoints после 30-дневного warm-up.
- Candidate: минимум 3 видео, 3 независимых канала и 2 свежих канала за 7 дней;
  specificity не ниже 70, thesis support не ниже 0,8.
- Одна topic identity учитывается как новый episode не чаще одного раза за 21 день.
- Future outcome внутри 21 дня должен одновременно дать:
  - не менее 3x rolling seven-day video supply;
  - не менее 3 новых независимых каналов;
  - не менее 5 новых стран и 8 стран всего;
  - не менее 50% новых видео;
  - минимум 24 часа lead time.
- Gate: минимум 20 положительных episodes, precision@10 не ниже 40%, median lead
  не ниже 7 дней, результат выше base rate и не хуже каждого простого baseline.

До outcome были раскрыты и записаны две поправки к data hygiene:

1. Явный non-English language code стал сильнее ASCII fallback; lowercase
   иностранное слово `ai` больше не считается токеном `AI`.
2. Повтор одной и той же незавершённой темы на соседних недельных checkpoints
   подавляется на 21 день, чтобы не раздувать sample size.

Score, outcome, temporal split и product gate после просмотра outcome не менялись.

## Data funnel

| Этап | Результат |
|---|---:|
| Исходные наблюдения | 71 940 519 |
| Строки после строгого English AI/tech admission | 20 060 |
| Уникальные видео | 168 |
| Уникальные каналы | 112 |
| Представленные страны | 72 |
| Stable topic identities, full archive | 45 |
| Stable topic identities, train | 38 |
| Train evidence rows | 15 126 |

Главное ограничение видно уже здесь: география широкая, но Trending-only archive
содержит всего 168 уникальных English AI-видео за три года. Это слишком узкий
candidate universe для надёжной оценки topic-level precision.

## Первичный результат

| Split | Недель | Eligible episodes | Predictions | Future positives | Precision |
|---|---:|---:|---:|---:|---:|
| Train | 97 | 0 | 0 | 0 | N/A |
| Blind holdout | 49 | 1 | 1 | 0 | 0% (n=1) |

В train не было ни одного topic episode, который одновременно прошёл evidence
floor. Поэтому train не мог калибровать ranking или сравнить его с baseline.

В holdout появился один episode:

- checkpoint: `2025-02-02 23:59:59 UTC`;
- label: `DeepSeek market activity`;
- deterministic score: `28.5`;
- baseline: 5 видео, 5 каналов и 6 стран;
- следующие 21 день: supply `1.0x`, 0 новых каналов, 0 новых стран, 0% новых
  видео;
- outcome: **не сработал**.

Evidence:

- [China's DeepSeek triggers global tech sell-off](https://www.youtube.com/watch?v=-KK8SuvwoRQ)
- [Big Tech in panic mode... Did DeepSeek R1 just pop the AI bubble?](https://www.youtube.com/watch?v=Nl7aCUsWykg)
- [Deepseek R1 Explained by a Retired Microsoft Engineer](https://www.youtube.com/watch?v=V-Fla5hxMRg)
- [DeepSeek is a Game Changer for AI — Computerphile](https://www.youtube.com/watch?v=gY4Z-9QlZ64)
- [China’s DeepSeek Sparks Global AI Race](https://www.youtube.com/watch?v=r3TpcHebtxM)

Это единичное наблюдение похоже на уже подтверждённую и насыщенную волну, а не на
ранний сигнал: к checkpoint тема уже имела пять независимых публикаций и шесть
Trending-рынков, после чего не расширилась. На основании одного эпизода нельзя
оценить общую precision, но он показывает риск: evidence floor в Trending-only
universe может давать confirmation слишком поздно.

## Sensitivity и robustness

Первичный holdout был независимо пересчитан локально и совпал с сохранённым
результатом бит-в-бит по metrics.

| Вариант | Checkpoints | Episodes | Positives | Method precision |
|---|---:|---:|---:|---:|
| Primary: 21 день, +5 стран | 49 | 1 | 0 | 0% |
| Horizon 14 дней | 49 | 1 | 0 | 0% |
| Horizon 30 дней | 47 | 1 | 0 | 0% |
| Country floor +3 | 49 | 1 | 0 | 0% |
| Country floor +10 | 49 | 1 | 0 | 0% |

Ни одна заранее объявленная descriptive sensitivity не превратила DeepSeek в
положительный outcome. Простые rankings по supply, country breadth, velocity,
view growth и seeded random видели тот же единственный кандидат, поэтому архив не
позволил сравнить discriminative ranking quality.

## Найденный taxonomy-дефект

Проверка format-neutrality удалила из исторических titles маркеры `tutorial`,
`review`, `hands-on`, `explained`, `demo`, `livestream`, `podcast`, `shorts` и
`reaction`.

- Проверено 18 видео с такими markers.
- Topic key не изменился у 17 из 18: **94,4%**.
- Нарушение: `GPT-4 Developer Livestream` после удаления `Livestream` стало
  `GPT-4 Developer` и получило другой topic key.

Следовательно, taxonomy v6 значительно уменьшила format bias, но обещание полной
format-neutrality пока не выполнено. Исправление должно получить новую версию
taxonomy и новый future cohort; задним числом переписывать этот holdout нельзя.

## Что этот тест доказал и чего не доказал

Доказано:

- point-in-time global replay технически воспроизводим;
- raw/filtered/code artifacts имеют SHA-256;
- train сохраняется до holdout;
- English/AI false admission для выявленных французских и албанских случаев
  исправлен;
- каждая prediction разрешается в конкретные YouTube evidence links;
- sensitivity не скрывает отрицательный результат.

Не доказано:

- что score ранжирует будущие виральные темы лучше baseline;
- что precision@10 близка к 40%;
- что метод даёт полезный lead time;
- что production stack работает на полном YouTube universe;
- что 0% на одном holdout episode является устойчивой оценкой precision.

## Итоговый product verdict

Маркетинговое утверждение «EarlySignal заранее предсказывает виральные темы» всё
ещё нельзя выпускать.

Текущий корректный claim: система умеет собирать evidence, формировать
subject/event identities и ранжировать подтверждающиеся темы, но predictive
quality пока эмпирически не валидирована.

Следующий решающий тест должен использовать не Trending-only архив, а полный
historical candidate universe релевантных AI-загрузок, включая невиральные видео,
с ранними view snapshots и channel-normalized baseline. До открытия нового
holdout нужно заранее обеспечить минимум 20 положительных topic episodes; иначе
precision и baseline lift снова останутся неизмеримыми.

## Воспроизводимость

- Source archive SHA-256:
  `4cda61820acd16f329e5b075887b26fb9d8526acd8ed5e4fb213c7d64ed6665f`
- Full filtered evidence SHA-256:
  `6439761a16750de25d68c0b8aa1595cee66a6249e109a2e2a847392cddc8e30d`
- Code/protocol SHA-256:
  `9e3f9b57a68f4c76a51f1e5a65e91f1a14de9cc837e6b2717dbc3f5f02a1aa0a`
- Primary protocol: `global-cross-market-replay-v1`
- Outcome: `cross-market-new-supply-country-diffusion-21d-v1`
- Taxonomy: `microtopic-clustering-v6-subject-event`

Связанные артефакты:

- `GLOBAL_CROSS_MARKET_BACKTEST_PREREGISTRATION_2026-08-09.md`
- `GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json` / `.md`
- `GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.json` / `.md`
- `GLOBAL_CROSS_MARKET_ROBUSTNESS_2026-08-09.json` / `.md`
- `global_ai_tech_filter_stats.json`
