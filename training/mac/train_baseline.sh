#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VENV_PATH="${VENV_PATH:-.venv-mac}"
VARIANT="${VARIANT:-standardized_256}"
SEED="${SEED:-42}"
MODEL="${MODEL:-mobilenet_v3_large}"
EPOCHS="${EPOCHS:-15}"
BATCH_SIZE="${BATCH_SIZE:-32}"
WORKERS="${WORKERS:-4}"
DEVICE="${DEVICE:-auto}"
RUN_NAME="${RUN_NAME:-}"

PYTHON_EXE="$REPO_ROOT/$VENV_PATH/bin/python"
if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "Python executable not found at $PYTHON_EXE. Run training/mac/setup_mac_training.sh first." >&2
  exit 1
fi

if [[ "$DEVICE" == "auto" ]]; then
  DEVICE="$("$PYTHON_EXE" -c 'import torch; print("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")')"
fi

echo "Using training device: $DEVICE"

"$PYTHON_EXE" training/verify_environment.py --expect-device any
"$PYTHON_EXE" training/prepare_dataset.py --variant "$VARIANT" --seed "$SEED"

TRAIN_ARGS=(
  training/train_classifier.py
  --train-manifest "datasets/manifests/four_class/$VARIANT/train.csv"
  --val-manifest "datasets/manifests/four_class/$VARIANT/val.csv"
  --test-manifest "datasets/manifests/four_class/$VARIANT/test.csv"
  --model "$MODEL"
  --epochs "$EPOCHS"
  --batch-size "$BATCH_SIZE"
  --workers "$WORKERS"
  --device "$DEVICE"
  --seed "$SEED"
)

if [[ -n "$RUN_NAME" ]]; then
  TRAIN_ARGS+=(--run-name "$RUN_NAME")
fi

"$PYTHON_EXE" "${TRAIN_ARGS[@]}"
