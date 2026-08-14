# Вердикт по основной гипотезе EarlySignal на 2026-08-09

## Короткий ответ

**Нет, рабочесть метода пока не доказана.** До этой проверки у проекта не было
полноценного historical backtest, который в прошлом времени выбирает темы, не
видит будущих данных, а затем проверяет, стали ли выбранные темы виральными.

Текущий статус гипотезы: **NOT VALIDATED**.

Новый full-universe YouNiverse replay не изменил этот статус. Из официального
архива примерно 72,9 млн English YouTube-видео после high-precision taxonomy
осталось 18 090 train-видео и 11 482 holdout-видео. Метод сформировал 52
train-эпизода и 16 holdout-эпизодов, но ни один не выполнил замороженный
42-дневный viral outcome. Все семь robustness-вариантов также дали 0 positives.
Формальный verdict — `INSUFFICIENT_OUTCOME_SUPPORT`; подробности и evidence:
`YOUNIVERSE_STRUCTURAL_BACKTEST_VERDICT_2026-08-09_RU.md`.

После исправления taxonomy v6 ответ не изменился: система стала значительно
лучше распознавать предмет и событие, но на доступных исторических архивах не
сформировала ни одного actionable-прогноза, который затем можно было бы честно
засчитать как предсказание виральной темы.

Новый global cross-market replay также не изменил ответ. Из 71 940 519
исторических Trending-наблюдений строгий фильтр оставил 168 уникальных English
AI/tech-видео и 45 topic identities. Train дал 0 eligible episodes; blind
holdout — один episode `DeepSeek market activity`, который не вырос в следующие
21 день. Формальный verdict — `INSUFFICIENT_OUTCOME_SUPPORT`. Полный разбор
находится в `GLOBAL_CROSS_MARKET_BACKTEST_VERDICT_2026-08-09_RU.md`.

## Что действительно было проверено

### 1. Production short-horizon replay

Для шести train-checkpoints были заранее сохранены top-10 прогнозов, после чего
они проверялись на наблюдениях через 1, 3 и 5 дней.

| Горизонт | Прогнозов | Оцениваемых | Сработало | Precision | Spearman score/outcome |
|---:|---:|---:|---:|---:|---:|
| 1 день | 60 | 27 | 0 | 0% | +0.099 |
| 3 дня | 50 | 22 | 0 | 0% | -0.168 |
| 5 дней | 30 | 13 | 0 | 0% | -0.102 |

Вывод: короткое наблюдение не подтвердило predictive quality. Более высокий
score не давал стабильно более сильного будущего результата. Покрытие follow-up
составило только 43–45%, поэтому этот тест является отрицательным диагностическим
сигналом, но не финальным 42-дневным вердиктом.

Источники результата:

- `EXPLORATORY_SHORT_HORIZON_RETROSPECTIVE_2026-08-08.md`;
- `TRAIN_RANKING_CALIBRATION_2026-08-08.md`.

### 2. Независимый 30-дневный time-series replay 2024

Был загружен независимый архив из 61 096 YouTube-видео с ежедневными view-count
snapshots. Протокол и даты были зафиксированы до просмотра outcome.

Первый запуск дал ноль actionable predictions, однако аудит показал дефект
адаптера: строка `ai` искалась как произвольная подстрока и пропускала не-AI
названия. Кроме того, выборка содержала слишком мало тематических видео для
измерения роста supply на уровне микротренда.

Поэтому исходный v1-запуск имеет статус **INVALID**, а не доказательство провала
или успеха продукта. Его артефакты сохранены, чтобы ошибка не была скрыта:

- `EXTERNAL_30D_BACKTEST_RESULT_2026-08-09.md`;
- `EXTERNAL_30D_BACKTEST_FUNNEL_DIAGNOSTIC_2026-08-09.json`.

После исправления token-aware admission и перехода на taxonomy v6 архив был
проигран повторно по тем же восьми checkpoint'ам:

- 61 096 видео с независимыми view-count time series;
- 216 видео прошли строгий AI/tech admission;
- 30 стабильных subject/event identities;
- 18 visible topic-checkpoints;
- actionable-прогнозов метода: **0**;
- тем, выполнивших заранее установленный outcome одновременно по 3x supply и
  3x normalized lift: **0**.

Product gate получил **FAIL**. Precision метода корректно обозначен как `N/A`,
а не 0%: при нуле прогнозов precision не определён. Архив также оказался
недискриминирующим для заданного outcome — положительных будущих исходов не было
даже среди простых baseline-кандидатов. Поэтому он исключает заявление об
успехе, но сам по себе не измеряет реальную precision на подходящем universe.

Актуальные артефакты:

- `EXTERNAL_30D_BACKTEST_RESULT_V6_2026-08-09.md`;
- `EXTERNAL_30D_BACKTEST_FUNNEL_DIAGNOSTIC_V6_2026-08-09.json`.

### 3. US YouTube Trending 2020–2024: v5 против v6

Независимый ежедневный архив US Trending содержит:

- 47 142 уникальных видео;
- 264 717 дневных snapshots;
- 28 роликов с явным AI/tech anchor в названии и релевантной категорией, которые
  реально вошли в US Trending;
- 146 дневных checkpoint'ов для этих видео.

Результат старой v5 taxonomy: 3 из 28 mapped, 1 visible, 0 actionable. Результат
новой v6 subject/event taxonomy: **28 из 28 mapped**, 19 visible на первом
Trending-наблюдении, 0 actionable.

Таким образом, конкретный admission-блокер исправлен: GPT-4, Microsoft 365
Copilot, OpenAI DevDay, Gemini, Google–ChatGPT competition и NVIDIA event теперь
получают стабильные, format-neutral identities. Но predictive validation всё
равно не получена:

- actionable checkpoint'ов: **0 из 146**;
- максимальный размер одной видимой исторической волны: 2 видео;
- максимальное число независимых каналов в одной волне: 2;
- production-порог в 3 независимых канала намеренно не ослаблялся.

Архив видит ролики уже после входа в Trending и не содержит universe
не-виральных кандидатов. Он доказывает исправление taxonomy coverage, но не
precision или lead time до виральности.

Полный построчный отчёт:

- `US_TRENDING_HISTORICAL_COVERAGE_2026-08-09.md` — сохранённый v5 baseline;
- `US_TRENDING_HISTORICAL_COVERAGE_V6_2026-08-09.md` — актуальный v6 replay.

### 4. Global cross-market Trending replay 2022–2025

Для более широкой проверки был использован независимый Global YouTube Trending
Dataset: 71 940 519 наблюдений, четыре snapshot в день и десятки национальных
рынков. Протокол, временной split и outcome были зафиксированы до открытия
holdout. Train был физически отделён и захеширован.

После строгого English AI/tech admission осталось:

- 20 060 строк evidence;
- 168 уникальных видео;
- 112 каналов;
- 72 страны;
- 45 stable topic identities.

На 97 train-checkpoints не сформировалось ни одного eligible topic episode. На
49 blind holdout-checkpoints появился один episode — `DeepSeek market activity`:
5 видео, 5 каналов и 6 стран на момент prediction. В следующие 21 день он не
добавил новых видео, каналов или стран и не выполнил frozen outcome.

Итог: 1 prediction, 0 positives, формальный verdict
`INSUFFICIENT_OUTCOME_SUPPORT`. Наблюдение не подтверждает predictive quality,
но одного episode недостаточно для статистически устойчивой оценки precision или
сравнения ranking с baseline. Архив также наблюдает темы уже после входа в
Trending и потому проверяет cross-market diffusion, а не самое раннее
предсказание до platform confirmation.

Robustness на горизонтах 14, 21 и 30 дней и при разных country floors не изменил
исход. Отдельно выявлен taxonomy-дефект: после удаления format-marker
`Livestream` один из 18 проверенных titles получил другой topic key. Исправлять
его нужно новой версией taxonomy и новым future cohort, не переписывая этот
holdout задним числом.

Актуальные артефакты:

- `GLOBAL_CROSS_MARKET_BACKTEST_VERDICT_2026-08-09_RU.md`;
- `GLOBAL_CROSS_MARKET_BACKTEST_PREREGISTRATION_2026-08-09.md`;
- `GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json`;
- `GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.json`;
- `GLOBAL_CROSS_MARKET_ROBUSTNESS_2026-08-09.json`.

### 5. Full-universe YouNiverse structural replay 2016–2019

YouNiverse устранил главный недостаток Trending-архивов: он содержит обычные и
успешные загрузки, то есть отрицательные кандидаты. Финальные просмотры были
доступны только outcome evaluator, а ranking использовал исторические metadata
и channel snapshots.

После train-only очистки неоднозначных anchors taxonomy v7.1 распознала 18 090
train-видео и 11 482 holdout-видео. Frozen feasibility rule выбрал policy
`3 канала / recent 14 дней`, не используя precision или будущие outcomes.

- train: 52 candidate episodes, 0 positives;
- holdout: 16 candidate episodes, 0 positives;
- precision@10: 0% в отчёте, но статистически неидентифицируема при нулевом
  positive support;
- prediction coverage: 81,25%; future-video baseline coverage: 94,25%;
- robustness: 8–18 candidates на вариант, везде 0 positives.

Отдельные partial signals существовали. Например, PyTorch дал три будущих
outlier-видео и median 2,4931x, но supply составил лишь 0,314x ожидаемого.
TensorFlow распространился на пять новых каналов, но supply был 0,8x, а не 3x.
Ни одна тема не совместила adoption breakout и сильные video outcomes.

Во время выполнения были обнаружены и сохранены два invalid-прогона: taxonomy
contamination и несоответствие `view_count`/`final_view_count`. После regression
fix полностью пересчитаны train, holdout и robustness с новым code hash. Из-за
необходимости открыть нулевой diagnostic report будущий формальный PASS всё
равно потребует нового temporal cohort.

Полный отчёт:

- `YOUNIVERSE_STRUCTURAL_BACKTEST_VERDICT_2026-08-09_RU.md`;
- `YOUNIVERSE_STRUCTURAL_BACKTEST_PREREGISTRATION_2026-08-09.md`;
- `youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_TRAIN_2026-08-09.json`;
- `youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_2026-08-09.json`;
- `youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_ROBUSTNESS_2026-08-09.json`.

## Чего нельзя утверждать

- Нельзя говорить, что EarlySignal уже предсказывает виральные темы.
- Нельзя называть 100% taxonomy mapping predictive recall: это разные метрики.
- Нельзя выдавать наличие карточек в UI или правдоподобные названия тем за
  predictive validation.
- Нельзя считать текущие 1/3/5-дневные нули финальным опровержением: окно короче
  целевого, а follow-up coverage недостаточно.
- Нельзя подменять topic-level prediction проверкой отдельных уже виральных
  роликов.

## Как выглядит честный тест основной гипотезы

Для каждого historical checkpoint метод должен:

1. Использовать только видео и метрики, существовавшие к моменту `t0`.
2. Построить микротренды, применить те же filters и ranking, что в production.
3. Сохранить top-10 до открытия будущего окна.
4. Через 42 дня независимо определить, выросли ли одновременно supply темы и
   channel-normalized outlier lift.
5. Сравнить метод с простыми baseline: supply, velocity, outlier и random.
6. Отдельно открыть заранее запечатанный holdout.

Заранее установленный product gate:

- минимум 6–8 checkpoints;
- `precision@10 >= 40%`;
- медианный lead time не меньше 21 дня;
- результат лучше base rate и не хуже простых baseline;
- не менее 80% прогнозов имеют достаточный direct follow-up.

## Когда появится первый валидный production-ответ

Production cohort уже заморожен: восемь checkpoints с 80 прогнозами, train 6 и
holdout 2. Их полные 42-дневные окна созревают с **2026-09-11 по 2026-09-18**.
До открытия holdout менять его правила или подбирать пороги по его результатам
нельзя.

## Что делать до сентября

1. Зафиксировать v6 taxonomy как отдельную версию. Не пересчитывать старый
   замороженный cohort задним числом и не менять его holdout по результатам
   просмотра.
2. Собрать или приобрести historical candidate-universe: не только Trending, а
   все найденные релевантные загрузки с point-in-time view snapshots. Без
   отрицательных кандидатов нельзя честно оценить precision до виральности.
3. Заморозить новый v6 cohort и проверять его ranking только после созревания
   окна, отдельно от старого v5 cohort.
4. Использовать train-период только для исправления taxonomy, topic identity и
   ranking. После фиксации кода открыть отдельный временной holdout один раз.
5. Не выпускать marketing claim о предсказании трендов, пока хотя бы один
   независимый или production holdout не пройдет gate.

## Итог

На сегодняшний день есть **реализованный механизм прогнозирования и исправленная
v6 taxonomy**, но нет эмпирического доказательства, что метод предсказывает
виральные темы с полезной точностью и достаточным опережением. Ни один из четырёх
независимых исторических архивов не дал положительного засчитываемого
topic-level outcome; production short-horizon replay также дал ноль срабатываний.
Гипотеза остаётся не подтверждённой, а полноценный blind test на
candidate-universe с позитивными и негативными исходами — обязательным quality
gate.
