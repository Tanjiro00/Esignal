#!/bin/sh
set -eu

EVAL_DIR=${1:-/opt/earlysignal-eval-youniverse-20260809}
SOURCE_DIR="$EVAL_DIR/source"
ARTIFACT_DIR="$EVAL_DIR/artifacts"
CODE_DIR="$EVAL_DIR/code"
IMAGE=${EARLYSIGNAL_EVAL_IMAGE:-earlysignal-api:latest}

mkdir -p "$ARTIFACT_DIR"

verify_source() {
  file=$1
  expected_size=$2
  expected_md5=$3
  actual_size=$(stat -c %s "$SOURCE_DIR/$file")
  if [ "$actual_size" != "$expected_size" ]; then
    echo "$file size mismatch: expected $expected_size, got $actual_size" >&2
    exit 1
  fi
  echo "$expected_md5  $SOURCE_DIR/$file" | md5sum -c -
  sha256sum "$SOURCE_DIR/$file" > "$SOURCE_DIR/$file.sha256"
}

verify_source yt_metadata_en.jsonl.gz 13636127630 0514b2ee52ffaa2c9c27c539038feb60
verify_source df_channels_en.tsv.gz 5960728 aa4d90892aeaae40089b5825c87607c8
verify_source df_timeseries_en.tsv.gz 571058429 689cf552e2a2c906ab7e41c01b2a8627

run_python() {
  docker run --rm \
    --network none \
    --cpus 6 \
    --memory 12g \
    -e PYTHONPATH=/eval/python-deps:/work \
    -v "$EVAL_DIR:/eval" \
    -v "$CODE_DIR:/work:ro" \
    -w /work \
    "$IMAGE" \
    /app/.venv/bin/python "$@"
}

run_python scripts/filter_youniverse_archive.py filter-ai \
  --source /eval/source/yt_metadata_en.jsonl.gz \
  --train-output /eval/artifacts/youniverse_ai_train.jsonl.gz \
  --holdout-output /eval/artifacts/youniverse_ai_holdout_sealed.jsonl.gz \
  --train-channels /eval/artifacts/youniverse_train_channels.txt \
  --holdout-channels /eval/artifacts/youniverse_holdout_channels_sealed.txt \
  --stats-output /eval/artifacts/youniverse_filter_stats_sealed.json

run_python scripts/filter_youniverse_archive.py filter-baselines \
  --source /eval/source/yt_metadata_en.jsonl.gz \
  --train-output /eval/artifacts/youniverse_baselines_train.jsonl.gz \
  --holdout-output /eval/artifacts/youniverse_baselines_holdout_sealed.jsonl.gz \
  --train-channels /eval/artifacts/youniverse_train_channels.txt \
  --holdout-channels /eval/artifacts/youniverse_holdout_channels_sealed.txt \
  --stats-output /eval/artifacts/youniverse_baseline_stats_sealed.json

run_python scripts/filter_youniverse_archive.py filter-channel-table \
  --source /eval/source/df_timeseries_en.tsv.gz \
  --train-output /eval/artifacts/youniverse_timeseries_train.tsv.gz \
  --holdout-output /eval/artifacts/youniverse_timeseries_holdout_sealed.tsv.gz \
  --train-channels /eval/artifacts/youniverse_train_channels.txt \
  --holdout-channels /eval/artifacts/youniverse_holdout_channels_sealed.txt \
  --stats-output /eval/artifacts/youniverse_timeseries_stats_sealed.json

run_python scripts/filter_youniverse_archive.py filter-channel-table \
  --source /eval/source/df_channels_en.tsv.gz \
  --train-output /eval/artifacts/youniverse_channels_train.tsv.gz \
  --holdout-output /eval/artifacts/youniverse_channels_holdout_sealed.tsv.gz \
  --train-channels /eval/artifacts/youniverse_train_channels.txt \
  --holdout-channels /eval/artifacts/youniverse_holdout_channels_sealed.txt \
  --stats-output /eval/artifacts/youniverse_channel_stats_sealed.json

sha256sum \
  "$ARTIFACT_DIR/youniverse_ai_train.jsonl.gz" \
  "$ARTIFACT_DIR/youniverse_ai_holdout_sealed.jsonl.gz" \
  "$ARTIFACT_DIR/youniverse_baselines_train.jsonl.gz" \
  "$ARTIFACT_DIR/youniverse_baselines_holdout_sealed.jsonl.gz" \
  "$ARTIFACT_DIR/youniverse_timeseries_train.tsv.gz" \
  "$ARTIFACT_DIR/youniverse_timeseries_holdout_sealed.tsv.gz" \
  "$ARTIFACT_DIR/youniverse_channels_train.tsv.gz" \
  "$ARTIFACT_DIR/youniverse_channels_holdout_sealed.tsv.gz" \
  > "$ARTIFACT_DIR/youniverse_filtered_artifacts.sha256"

echo "YouNiverse filtering complete; sealed holdout artifacts were not analyzed."
