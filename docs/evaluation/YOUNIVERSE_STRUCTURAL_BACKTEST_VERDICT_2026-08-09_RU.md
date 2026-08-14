# Вердикт YouNiverse structural backtest EarlySignal

**Дата:** 2026-08-09  
**Формальный verdict:** `INSUFFICIENT_OUTCOME_SUPPORT`  
**Продуктовый статус гипотезы:** `NOT VALIDATED`  
**Источник:** [YouNiverse v1.1](https://doi.org/10.5281/zenodo.4650046)

## Короткий ответ

Нет, этот ретротест **не подтвердил**, что текущий structural metadata-only
метод EarlySignal заранее находит темы, которые затем становятся виральными.

На train система сформировала 52 кандидатных topic-эпизода, на holdout — 16.
Ни один эпизод не выполнил замороженное определение breakout: рост supply не
меньше 3x, распространение минимум на три новых канала и одновременно сильные
channel-normalized результаты будущих видео.

Это не следует интерпретировать как точную оценку реальной precision, равную
нулю. В проверяемой выборке не было ни одного положительного outcome, поэтому
precision, recall и lead time нельзя статистически оценить. Корректный вывод:
**доказательства predictive quality нет, а текущий test universe не поддерживает
заранее заданный product gate**.

## Что именно проверялось

Метод еженедельно воспроизводился в историческом времени и получал только:

- заголовок, описание, теги, канал и дату публикации, известные к checkpoint;
- channel time series не позднее checkpoint;
- структурные признаки supply, acceleration, channel spread и new-channel
  spread.

Финальные просмотры видео были физически отделены от candidate-side типов и
использовались только после сохранения ranking для расчёта outcome.

Проверялась узкая гипотеза: способен ли **структурный metadata-only slice** без
исторической view velocity ранжировать конкретные AI/tech-темы до их 42-дневного
роста. Это не тест полного production stack с ежедневными view snapshots,
комментариями, transcript evidence и cross-source demand.

## Данные и split

Исходный YouNiverse содержит около 72,9 млн English YouTube-видео и около 136
тыс. каналов. Размеры и опубликованные MD5 трёх исходных файлов совпали.

| Split | Checkpoints | Видео после taxonomy v7.1 | Topic identities |
|---|---:|---:|---:|
| Train, 2016-01-03 — 2018-11-18 | 151 | 18 090 | 114 |
| Holdout, 2019-01-06 — 2019-09-08 | 36 | 11 482 | 112 |

Первичный AI/tech archive filter пропустил 42 173 train-видео. Train-аудит
обнаружил и удалил неоднозначные совпадения: `Gemini`-астрологию, Behringer
`DeepMind`, обычные слова `gan`/`keras`, personal-name `Bert`/`Claude` и
нейролингвистическое программирование `NLP`. Итоговая taxonomy версия —
`microtopic-clustering-v7.1-format-neutral-historical-ai`.

Primary policy (`3 канала / recent 7 дней`) дал только 32 корректных train-
эпизода. По заранее записанной feasibility-лестнице, не используя precision,
был выбран первый достаточный вариант:

- минимум 3 канала;
- recent window 14 дней;
- active window 35 дней;
- saturation ceiling 25 видео;
- cooldown 42 дня.

Он дал 52 train-эпизода и 100% требуемого train outcome coverage.

## Замороженный outcome

Тема считается положительным breakout только при одновременном выполнении всех
условий в следующие 42 дня:

1. supply не меньше 3x ожидаемого;
2. минимум три будущих видео;
3. минимум три новых для темы канала;
4. минимум 50% будущих видео от новых каналов;
5. минимум три будущих видео с channel-normalized outlier ratio не меньше 3x;
6. медианный outlier ratio не меньше 2x;
7. baseline coverage не меньше 80%.

Порог успеха теста также был зафиксирован заранее: минимум 20 positive episodes,
precision@10 не меньше 40%, median lead не меньше 21 дня, превышение base rate и
результат не хуже простых baseline.

## Результат

| Метрика | Train | Holdout | Gate |
|---|---:|---:|---:|
| Candidate episodes | 52 | 16 | — |
| Positive outcomes | 0 | 0 | >=20 |
| Candidate base rate | 0% | 0% | — |
| Method precision@10 | 0%* | 0%* | >=40% |
| Median lead | N/A | N/A | >=21 дней |
| Prediction outcome coverage | 100% | 81,25% | >=80% |
| Future-video baseline coverage | 100% | 94,25% | >=80% |
| Verdict | `TRAIN_DIAGNOSTIC` | `INSUFFICIENT_OUTCOME_SUPPORT` | `PASS` не достигнут |

`*` В машиночитаемом отчёте при 0 срабатываниях записан 0%. Для продуктовой
интерпретации precision неидентифицируема: положительных outcomes в universe
нет, поэтому отделить качество ranking от отсутствия support невозможно.

Все простые baseline — supply, acceleration, channel spread и seeded random —
также получили 0 positives. Следовательно, EarlySignal их формально не хуже, но
это тривиальное равенство 0:0, а не доказательство преимущества.

## Что система увидела, но не смогла засчитать

### PyTorch: сильные отдельные видео без роста темы

На checkpoint 2019-02-24 тема `PyTorch creator activity` имела три будущих
видео с outlier ratio >=3x и медианный ratio 2,4931x. Но будущий supply составил
только 0,314x ожидаемого, и новых для темы каналов не было. Это video-level
outperformance без topic-level breakout.

Evidence до checkpoint:
[Dynamic Neural Network Programming with PyTorch](https://www.youtube.com/watch?v=CNuI8OWsppg).

### TensorFlow: распространение без ускорения supply

На checkpoint 2019-05-26 `TensorFlow creator activity` получил пять новых
каналов и 58,33% будущих видео от новых каналов. Однако supply составил 0,8x,
outlier-видео было два вместо трёх, медиана — 1,8296x вместо 2x.

Evidence до checkpoint:
[Reinforcement Learning with TensorFlow & TRFL](https://www.youtube.com/watch?v=s4Lcf9du9L8).

Максимальный supply growth среди 16 holdout predictions составил 1,167x, а не
требуемые 3x:
[Interactive Chatbots with TensorFlow](https://www.youtube.com/watch?v=zOCVTPb5DiM).

### OpenAI: новые каналы без будущих outliers

На checkpoint 2019-02-24 `OpenAI creator activity` имел четыре будущих видео от
четырёх новых каналов, то есть new-channel share 100%. Но supply был 0,667x,
outlier-видео >=3x не было, медиана составила 1,9526x.

Evidence до checkpoint:
[OpenAI — Learning Dexterous In-Hand Manipulation](https://www.youtube.com/watch?v=6fo5NhnyR8I).

Эти примеры показывают, почему UI-карточка может выглядеть содержательно, но это
ещё не означает, что тема предсказана как виральная.

## Robustness

Primary holdout был сохранён и захеширован до robustness. Ни одна соседняя
конфигурация не создала положительного outcome.

| Вариант | Candidates | Positives | Precision | Verdict |
|---|---:|---:|---:|---|
| minimum channels = 5 | 8 | 0 | 0% | insufficient |
| maximum active videos = 15 | 14 | 0 | 0% | insufficient |
| cooldown = 28 дней | 17 | 0 | 0% | insufficient |
| cooldown = 56 дней | 15 | 0 | 0% | insufficient |
| recent window = 7 дней | 11 | 0 | 0% | insufficient |
| maximum active videos = 40 | 16 | 0 | 0% | insufficient |
| minimum channels = 2 | 18 | 0 | 0% | insufficient |

Вывод устойчив к допустимым изменениям candidate floor: проблема не в одном
случайно неудачном пороге ranking.

## Обнаруженные execution defects

### 1. Taxonomy contamination

Первый train-аудит показал ложные предметы (`Gemini`-астрология, GAN-кубики,
Behringer DeepMind и т. д.). Они исправлены на train по заранее разрешённому
semantic-cleanup правилу; синтетические regression-тесты добавлены.

### 2. Outcome adapter считывал просмотры как нули

Фильтр сохранял raw `view_count` под provenance-именем `final_view_count`, а
replay adapter сначала принимал только raw-имя. Первый replacement holdout
поэтому имел нулевые view counts и был признан `INVALID_ZERO_OUTCOMES`.

Adapter теперь принимает обе схемы; candidate-side объекты по-прежнему не
содержат final engagement. После исправления полностью пересчитаны train,
holdout и robustness с новым code hash.

Поскольку нулевой отчёт пришлось открыть для диагностики, исправленный holdout
нельзя рекламировать как безупречно untouched confirmatory test. Реальные
ненулевые outcome labels до schema fix не использовались ranking-методом, но
формальный будущий `PASS` всё равно должен быть подтверждён на новом временном
cohort или другом неоткрытом dataset.

## Почему тест не дал достаточного support

1. **Outcome слишком редок для этого universe.** Он требует одновременно
   supply breakout, new-channel diffusion и несколько сильных видео. Ни один из
   68 train+holdout candidate episodes не выполнил все условия.
2. **YouNiverse смещён к уже известным каналам.** Dataset преимущественно
   содержит English-каналы с примерно 10 тыс.+ подписчиков и 10+ видео,
   известные Channel Crawler/Social Blade. Маленькие новые creators, которые
   особенно важны для early diffusion, представлены хуже.
3. **Нет point-in-time video velocity.** Финальные crawl-time views годятся для
   outcome, но structural ranker не видит раннее ускорение конкретных видео.
4. **Topic universe зависит от eligibility.** Отчёт хорошо проверяет исходы
   карточек, которые метод уже допустил, но не строит независимый полный каталог
   всех будущих breakout-эпизодов. Поэтому он слабее для оценки recall.
5. **Исторические topic identities всё ещё широки.** `TensorFlow creator
   activity` или `OpenAI creator activity` конкретнее общего AI, но шире
   продуктового микротренда, который нужен пользователю сегодня.

## Что этот результат разрешает утверждать

- Реализован воспроизводимый point-in-time replay с отрицательными кандидатами,
  evidence URLs, train/holdout split, simple baselines и SHA-256 artifacts.
- В текущем YouNiverse universe structural метод **не продемонстрировал** ни
  одного предсказанного вирального topic breakout.
- Текущий marketing claim «предсказываем виральные темы» не подтверждён.
- Отдельные структурные признаки находят partial signals, но их полезность для
  creator decision пока не доказана outcome-данными.

Нельзя утверждать, что метод доказанно бесполезен во всех условиях: тест не
содержит достаточной положительной выборки и не проверяет полный production
stack с view velocity. Но отсутствие доказательства после нескольких
независимых replay — уже критический продуктовый риск, а не формальность.

## Следующий корректный эксперимент

Следующую версию нельзя получать ослаблением этого holdout задним числом. Нужен
новый preregistered cohort:

1. Сформировать независимый topic-week universe до применения EarlySignal
   eligibility и разметить outcomes для всех тем, чтобы измерять recall и base
   rate независимо от метода.
2. Использовать ежедневные point-in-time video views и velocity минимум за
   12–18 месяцев, включая невиральные ролики и небольшие каналы.
3. На train отдельно изучить два outcome: **topic adoption breakout** и
   **creator-normalized video outperformance**. Затем заранее заморозить
   составной product label на новом holdout.
4. Гарантировать минимум 20, лучше 50+ positive episodes до сравнения precision.
5. Сравнивать score не только с supply/channel/random, но и с простым
   early-video-velocity baseline.
6. До прохождения gate показывать такие карточки в продукте как `Research
   candidate` или `Watch`, а не как доказанную рекомендацию к съёмке.

## Артефакты и воспроизводимость

- [Пререгистрация](YOUNIVERSE_STRUCTURAL_BACKTEST_PREREGISTRATION_2026-08-09.md)
- [Train report](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_TRAIN_2026-08-09.md)
- [Train JSON](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_TRAIN_2026-08-09.json)
- [Selected policy](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_SELECTED_POLICY_2026-08-09.json)
- [Holdout report](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_2026-08-09.md)
- [Holdout JSON](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_2026-08-09.json)
- [Robustness report](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_ROBUSTNESS_2026-08-09.md)
- [Robustness JSON](youniverse_2026-08-09/YOUNIVERSE_STRUCTURAL_HOLDOUT_ROBUSTNESS_2026-08-09.json)

Code/protocol SHA-256:
`e65589464d4bbb4d233651cca09be7ec139930dca973e2d2ffe78dc655553904`.

Архив всех финальных отчётов:
`youniverse_final_reports_20260809.tar.gz`, SHA-256
`2155c71d4137a21dbbd3212c046902fc685991324c034c9cdaa84bed3badcb5f`.

Все train, holdout и robustness manifests проверены локально и на изолированном
серверном evaluation-стенде.

## Итог

На вопрос «применили ли мы метод к прошлому и показал ли он, что заранее находил
виральные темы?» ответ сейчас такой:

**Метод к прошлому применён на большом candidate universe, но ни одной
подтверждённой виральной темы он в этом тесте не предсказал. Из-за нулевого числа
положительных outcomes гипотеза не подтверждена, а точная predictive precision
остаётся неизвестной.**
