#!/bin/bash -l
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:?Set PROJECT_ROOT to the TrashformerPro repo path on SCC.}"
VENV_PATH="${VENV_PATH:?Set VENV_PATH to the SCC virtualenv path.}"
PYTHON_MODULE="${PYTHON_MODULE:-python3/3.10.12}"
VARIANT="${VARIANT:-standardized_256}"
SEED="${SEED:-42}"
MODEL="${MODEL:-mobilenet_v3_large}"
EPOCHS="${EPOCHS:-15}"
BATCH_SIZE="${BATCH_SIZE:-128}"
WORKERS="${WORKERS:-8}"
DEVICE="${DEVICE:-cuda}"

if ! type module >/dev/null 2>&1; then
  source /etc/profile.d/modules.sh
fi

module load "${PYTHON_MODULE}"
source "${VENV_PATH}/bin/activate"

cd "${PROJECT_ROOT}"

python training/verify_environment.py --expect-device cuda
python training/prepare_dataset.py --variant "${VARIANT}" --seed "${SEED}"

python training/train_classifier.py \
  --train-manifest "datasets/manifests/four_class/${VARIANT}/train.csv" \
  --val-manifest "datasets/manifests/four_class/${VARIANT}/val.csv" \
  --test-manifest "datasets/manifests/four_class/${VARIANT}/test.csv" \
  --model "${MODEL}" \
  --epochs "${EPOCHS}" \
  --batch-size "${BATCH_SIZE}" \
  --workers "${WORKERS}" \
  --device "${DEVICE}" \
  --seed "${SEED}"
