# Что дальше: остаток плана

Состояние на 2026-08-15. Полный контекст и обоснование решений —
в [docs/ARCHITECTURE_V2_RU.md](docs/ARCHITECTURE_V2_RU.md), продуктовый план —
в плане до первых платящих.

---

## Что уже работает на проде

Сервер `45.129.124.109`, проект `earlysignal`, код в `/opt/earlysignal`
(зеркало чистого клона `/opt/esignal`).

| Компонент | Состояние |
|---|---|
| Панель каналов | 2 966 активных, восстановима на любую прошлую дату |
| Обход по RSS | работает, в cron ежедневно в 02:17 |
| Сбор комментариев | 38k+, в cron каждые 6 часов |
| Эмбеддинги | 12 000 (комментарии + ролики), `text-embedding-3-small`, 256 dim |
| Движок demand items | 65 кластеров → 28 верифицировано → 12 неотвеченных |
| API `/demand/feed` | отдаёт ленту с доказательствами, за авторизацией |
| Образы api/worker | собраны из исходников, `es_core` внутри |

Ядро `es_core/` — 41 тест, mypy strict. Правила панели `es_ingest/panel.py` —
11 тестов.

---

## Остаток: два пункта

### 1. Нишевый гейт панели — блокирующий

**Проблема.** В `scripts/refresh_panel.py` стоит заглушка:

```python
niche_share=1.0 if uploads.get(channel_id, 0) else 0.0
```

Нишевая принадлежность не измеряется, поэтому в панель зашёл каждый активный
канал из базы, а не каналы AI/tech. Последствие видно в выдаче: из 12 верхних
items к нише относятся два, остальное — хиджаб, Linux-ноутбуки, пост при
диабете, «как называется песня».

Движок при этом отработал честно — он нашёл настоящий неотвеченный спрос в той
совокупности, которую ему дали.

**Что сделать.**

1. Посчитать нишевый центроид: среднее эмбеддингов роликов заведомо нишевых
   каналов (взять 20–30 руками, либо ролики с якорями вроде `claude`, `openai`,
   `comfyui`). Эмбеддинги уже есть в `video_embeddings` с версией
   `video-embedding-openai-v1`.
2. Для каждого канала посчитать долю роликов за 90 дней с косинусом к центроиду
   выше порога. Порог **измерить**, а не назначить: посмотреть распределение
   для заведомо нишевых и заведомо чужих каналов и взять точку разделения.
3. Подставить измеренную долю в `ChannelEvidence.niche_share`.
4. Прогнать `refresh_panel --apply`. Правила уже написаны и покрыты тестами:
   вход при доле ≥ 0.5, выход при < 0.3, причина ухода `off_niche`. История
   сохранится, каналы не удалятся.
5. Пересобрать ленту и проверить гейт: **≥80% items релевантны нише**.

*Оценка:* полдня. Всё нужное уже есть, писать надо только расчёт доли.

### 2. Фронт: `/today` на ленту спроса

Бэкенд готов, фронт наполовину: типы, клиент `getDemandFeed` и компонент
`apps/web/components/demand/demand-feed.tsx` написаны, но `/today` всё ещё
рендерит старые сигналы.

**Что сделать.**

1. Переключить `apps/web/app/today/page.tsx` на `<DemandFeed />`.
2. Переделать `apps/web/app/opportunities/[signalId]/page.tsx` под карточку
   с комментариями-доказательствами.
3. Выключить флагами `FEATURE_UX_*`: `/signals`, `/pulse`, `/results`,
   `/watchlists`, `/briefs`, `/outcomes`, все `/admin/*` кроме `operations`.
   Код не удалять.
4. Гейт: от регистрации до первого «беру» — меньше трёх минут.

*Оценка:* 2–3 дня.

---

## Известные проблемы

**Верификация недетерминирована.** Модель `gpt-5.6-terra` не принимает
`temperature: 0`, параметр убран. Два прогона на одних данных дали 27 и 28
принятых items из 65. Разница мала, но детерминизм был проектным требованием.
Лечится сменой модели верификатора либо кэшированием вердикта по хешу входа.

**Репозиторий публичный.** `Tanjiro00/Esignal` создан как public. Секретов там
нет (`.env` в `.gitignore`, проверено поиском по значениям), но лежат аудит,
стратегия с ценами и замороженная исследовательская когорта. Переключается в
настройках GitHub.

**Диск сервера.** В `/opt/earlysignal` 27 ГБ `evaluation_data`, 7.8 ГБ
`backups`, 2.5 ГБ `releases`. На сборку не влияет — `.dockerignore` их
исключает, — но 38 ГБ при 59% занятости стоит разобрать.

**Старый чекаут `/opt/earlysignal/.git` сломан:** `git log` там виснет
(`timeout` убивает по 20 с). Рабочий клон — `/opt/esignal`, оттуда rsync.

---

## Команды

```bash
# выкатка: клон → зеркало → сборка → перезапуск
git -C /opt/esignal pull origin main
rsync -a --exclude=.git --exclude=node_modules --exclude=.venv --exclude=".env*" \
  /opt/esignal/ /opt/earlysignal/
cd /opt/earlysignal
docker compose --env-file .env.production -f docker-compose.production.yml build api worker
docker compose --env-file .env.production -f docker-compose.production.yml up -d api worker

# миграции
docker exec earlysignal-api-1 sh -lc 'cd /app && uv run alembic upgrade head'

# панель и сбор
docker exec earlysignal-api-1 sh -lc 'cd /app && uv run python -m scripts.refresh_panel --apply'
docker exec earlysignal-api-1 sh -lc 'cd /app && uv run python -m scripts.crawl_panel --limit 3000 --apply'
docker exec earlysignal-api-1 sh -lc 'cd /app && uv run python -m scripts.crawl_comments --limit 400 --selection panel --apply'

# лента спроса
docker exec earlysignal-api-1 sh -lc 'cd /app && uv run python -m scripts.build_demand_feed --window 30'

# локальные проверки
uv run pytest tests/es_core tests/es_ingest tests/unit -q
uv run mypy es_core es_ingest
uv run ruff check es_core es_eval es_ingest apps scripts
```

Откат образов: предыдущие лежат с тегом `pre-shadow-audit-20260813T1810Z`.

---

## Правило, которое стоит соблюдать

За время работы трижды подряд порог, назначенный на глаз, оказывался неверным:
балл якоря 8.0, шкала fit из видео-пространства, перемножение компонент разного
масштаба. Каждый раз чинилось замером, а не подбором.

Поэтому в коде каждый порог сопровождается тем, на чём он измерен. Новые пороги
добавлять так же: сначала посмотреть распределение, потом взять число.
