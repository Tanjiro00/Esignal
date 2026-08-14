#!/usr/bin/env bash
set -euo pipefail

evaluation_root="${1:?evaluation root is required}"
filter_pid="${2:-}"
data_root="/opt/earlysignal/evaluation_data"
dataset_path="${data_root}/global_ai_tech_evidence.csv.gz"
train_dataset_path="${data_root}/global_ai_tech_train_evidence.csv.gz"
source_hash_path="${data_root}/youtube_trends.tar.bz2.sha256"

if [[ -n "${filter_pid}" ]]; then
  while kill -0 "${filter_pid}" 2>/dev/null; do
    sleep 30
  done
fi

test -s "${dataset_path}"
test -s "${train_dataset_path}"
test -s "${source_hash_path}"
source_sha256="$(cut -d ' ' -f 1 "${source_hash_path}")"
cd "${evaluation_root}"

docker run --rm \
  --volume "${evaluation_root}:/evaluation:ro" \
  --volume "${data_root}:/data" \
  --workdir /evaluation \
  --env PYTHONPATH=/evaluation \
  earlysignal-api:latest \
  /app/.venv/bin/python -m scripts.run_global_cross_market_backtest \
  --dataset /data/global_ai_tech_train_evidence.csv.gz \
  --split train \
  --source-sha256 "${source_sha256}" \
  --json-output /data/GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json \
  --markdown-output /data/GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.md
sha256sum "${data_root}/GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json" \
  >"${data_root}/GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json.sha256"

# The holdout is opened only after the immutable train artifact above exists.
test -s "${data_root}/GLOBAL_CROSS_MARKET_TRAIN_2026-08-09.json.sha256"
docker run --rm \
  --volume "${evaluation_root}:/evaluation:ro" \
  --volume "${data_root}:/data" \
  --workdir /evaluation \
  --env PYTHONPATH=/evaluation \
  earlysignal-api:latest \
  /app/.venv/bin/python -m scripts.run_global_cross_market_backtest \
  --dataset /data/global_ai_tech_evidence.csv.gz \
  --split holdout \
  --source-sha256 "${source_sha256}" \
  --json-output /data/GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.json \
  --markdown-output /data/GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.md
sha256sum "${data_root}/GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.json" \
  >"${data_root}/GLOBAL_CROSS_MARKET_HOLDOUT_2026-08-09.json.sha256"
