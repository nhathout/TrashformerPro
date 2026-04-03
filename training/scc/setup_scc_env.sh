#!/bin/bash -l
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <project_space_dir> <repo_root> [python_module]" >&2
  echo "Example: $0 /projectnb/myproject /projectnb/myproject/TrashformerPro python3/3.10.12" >&2
  exit 1
fi

PROJECT_SPACE_DIR="$1"
REPO_ROOT="$2"
PYTHON_MODULE="${3:-python3/3.10.12}"
VENV_PATH="${PROJECT_SPACE_DIR}/venvs/trashformerpro-cu126"
TORCH_VERSION="${TORCH_VERSION:-2.6.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.21.0}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu126}"

if ! type module >/dev/null 2>&1; then
  source /etc/profile.d/modules.sh
fi

module load "${PYTHON_MODULE}"

mkdir -p "${PROJECT_SPACE_DIR}/venvs"
python -m venv "${VENV_PATH}"
source "${VENV_PATH}/bin/activate"

python -m pip install --upgrade pip
python -m pip install "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" --index-url "${TORCH_INDEX_URL}"
python -m pip install -r "${REPO_ROOT}/training/requirements.txt"
cd "${REPO_ROOT}"
python "${REPO_ROOT}/training/verify_environment.py"

echo
echo "SCC environment ready."
echo "Activate with:"
echo "  module load ${PYTHON_MODULE}"
echo "  source ${VENV_PATH}/bin/activate"
