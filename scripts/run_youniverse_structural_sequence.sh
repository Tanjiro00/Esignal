#!/bin/sh
set -eu

EVAL_DIR=${1:-/opt/earlysignal-eval-youniverse-20260809}
ARTIFACT_DIR="$EVAL_DIR/artifacts"
CODE_DIR="$EVAL_DIR/code"
IMAGE=${EARLYSIGNAL_EVAL_IMAGE:-earlysignal-api:latest}

case ${2:-train} in
  train)
    split=train
    ;;
  holdout)
    split=holdout
    ;;
  robustness)
    split=robustness
    ;;
  *)
    echo "usage: $0 [eval-dir] [train|holdout|robustness]" >&2
    exit 2
    ;;
esac

docker run --rm \
  --network none \
  --cpus 6 \
  --memory 12g \
  -e PYTHONPATH=/work \
  -v "$EVAL_DIR:/eval" \
  -v "$CODE_DIR:/work:ro" \
  -w /work \
  "$IMAGE" \
  /app/.venv/bin/python scripts/run_youniverse_structural_evaluation.py \
    --eval-dir /eval \
    --split "$split"
