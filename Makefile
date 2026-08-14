SHELL := /bin/bash

.PHONY: setup demo service api web worker migrate seed-demo seed-queries ingest-real run-ingestion refresh-video-intelligence run-snapshots build-signals backfill-lifecycle-history backfill-snapshot-buckets backfill-derived-metrics refresh-demand refresh-transcripts benchmark-providers generate-digest refresh-outcomes sync-owned-analytics expand-queries export-evaluation export-backtest-checkpoint freeze-backtest-cohort run-backtest-evaluation audit-semantic-release-queue backup verify-backup restore-backup production-preflight format lint typecheck test test-e2e build check clean-demo

setup:
	uv sync --all-groups
	npm install
	npx playwright install chromium

migrate:
	uv run alembic upgrade head

seed-demo: migrate
	DEMO_MODE=true uv run python -m apps.api.seed

seed-queries: migrate
	uv run python -m apps.worker seed-queries

ingest-real: migrate
	uv run python -m apps.worker run-query "AI coding agents" --force --limit 20

run-ingestion: migrate
	uv run python -m apps.worker run-due --limit 5

refresh-video-intelligence: migrate
	uv run python -m apps.worker refresh-video-intelligence --limit 50

run-snapshots: migrate
	uv run python -m apps.worker run-snapshots --limit 50

build-signals: migrate
	uv run python -m apps.worker build-signals --force

backfill-lifecycle-history: migrate
	uv run python -m apps.worker backfill-lifecycle-history --source $(if $(SOURCE),$(SOURCE),live)

backfill-snapshot-buckets: migrate
	uv run python -m apps.worker backfill-snapshot-buckets --source $(if $(SOURCE),$(SOURCE),live)

backfill-derived-metrics: migrate
	uv run python -m scripts.backfill_derived_metric_points

refresh-demand: migrate
	uv run python -m apps.worker run-demand --force --limit 12

refresh-transcripts: migrate
	uv run python -m apps.worker run-transcripts --force --limit 8

benchmark-providers: migrate
	uv run python -m apps.worker benchmark-providers --live --limit 3

generate-digest: migrate
	uv run python -m apps.worker generate-digest $(if $(WORKSPACE_ID),--workspace-id $(WORKSPACE_ID),)

refresh-outcomes: migrate
	uv run python -m apps.worker refresh-outcomes $(if $(WORKSPACE_ID),--workspace-id $(WORKSPACE_ID),)

sync-owned-analytics: migrate
	uv run python -m apps.worker sync-owned-analytics $(if $(WORKSPACE_ID),--workspace-id $(WORKSPACE_ID),)

expand-queries: migrate
	uv run python -m apps.worker expand-queries

export-evaluation:
	uv run python scripts/export_manual_evaluation.py --kind $(if $(KIND),$(KIND),labels) --format $(if $(FORMAT),$(FORMAT),jsonl) --output $(if $(OUTPUT),$(OUTPUT),var/evaluation-export.jsonl)

export-backtest-checkpoint: migrate
	@if [ -z "$(AS_OF)" ]; then echo "AS_OF is required"; exit 2; fi
	uv run python -m scripts.export_backtest_checkpoint \
		--as-of "$(AS_OF)" \
		--source-kind $(if $(SOURCE),$(SOURCE),live) \
		--source-environment $(if $(ENVIRONMENT),$(ENVIRONMENT),local) \
		--output $(if $(OUTPUT),$(OUTPUT),var/backtest/checkpoint.json) \
		$(if $(PERSIST),--persist,)

freeze-backtest-cohort: migrate
	uv run python -m scripts.freeze_backtest_cohort \
		--as-of "$(if $(AS_OF),$(AS_OF),$(shell date -u +%Y-%m-%dT%H:%M:%SZ))" \
		--source-kind $(if $(SOURCE),$(SOURCE),live) \
		--source-environment $(if $(ENVIRONMENT),$(ENVIRONMENT),local) \
		--name "$(if $(NAME),$(NAME),historical baseline cohort)" \
		--checkpoint-count $(if $(CHECKPOINT_COUNT),$(CHECKPOINT_COUNT),8) \
		--holdout-count $(if $(HOLDOUT_COUNT),$(HOLDOUT_COUNT),2) \
		--output-json $(if $(OUTPUT_JSON),$(OUTPUT_JSON),var/backtest/cohort.json) \
		--output-markdown $(if $(OUTPUT_MD),$(OUTPUT_MD),var/backtest/cohort.md) \
		$(if $(FREEZE),--freeze,)

run-backtest-evaluation: migrate
	@if [ -z "$(CHECKPOINT_IDS)" ]; then echo "CHECKPOINT_IDS is required"; exit 2; fi
	uv run python -m scripts.run_backtest_evaluation \
		--checkpoint-ids "$(CHECKPOINT_IDS)" \
		--evaluation-as-of "$(if $(EVALUATION_AS_OF),$(EVALUATION_AS_OF),$(shell date -u +%Y-%m-%dT%H:%M:%SZ))" \
		--output $(if $(OUTPUT),$(OUTPUT),var/backtest/report.md) \
		--name "$(if $(NAME),$(NAME),temporal backtest)"

audit-semantic-release-queue:
	@if [ -z "$(SOURCE)" ]; then echo "SOURCE is required"; exit 2; fi
	uv run python -m scripts.audit_semantic_release_queue \
		--source "$(SOURCE)" \
		--output "$(if $(OUTPUT),$(OUTPUT),var/evaluation/semantic-adoption-agent-audit.json)" \
		--limit "$(if $(LIMIT),$(LIMIT),8)"

backup:
	./scripts/backup.sh

verify-backup:
	./scripts/verify_backup.sh

restore-backup:
	@if [ -z "$(BACKUP_FILE)" ]; then echo "BACKUP_FILE is required"; exit 2; fi
	./scripts/restore_backup.sh "$(BACKUP_FILE)"

production-preflight:
	./scripts/production_preflight.sh $(if $(ENV_FILE),$(ENV_FILE),.env.production)

api:
	DEMO_MODE=true uv run uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

web:
	npm run dev

worker:
	uv run python -m apps.worker serve

demo: seed-demo
	@trap 'kill 0' INT TERM EXIT; \
	DEMO_MODE=true uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 & \
	NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev

service: migrate seed-queries
	@trap 'kill 0' INT TERM EXIT; \
	DEMO_MODE=true uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 & \
	uv run python -m apps.worker serve & \
	NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev

format:
	uv run ruff format .
	uv run ruff check --fix .
	npm run format

lint:
	uv run ruff format --check .
	uv run ruff check .
	npm run lint
	npm run format:check

typecheck:
	uv run mypy apps packages
	npm run typecheck

test:
	uv run pytest
	npm run test:web

test-e2e:
	npm run test:e2e

build:
	npm run build

check: lint typecheck test build

clean-demo:
	DEMO_MODE=true uv run python -m apps.api.seed --reset-only
