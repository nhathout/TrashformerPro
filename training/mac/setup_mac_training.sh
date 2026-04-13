#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PATH="${VENV_PATH:-.venv-mac}"
TORCH_VERSION="${TORCH_VERSION:-2.6.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.21.0}"

"$PYTHON_BIN" -m venv "$VENV_PATH"

PYTHON_EXE="$REPO_ROOT/$VENV_PATH/bin/python"

"$PYTHON_EXE" -m pip install --upgrade pip
"$PYTHON_EXE" -m pip install "torch==$TORCH_VERSION" "torchvision==$TORCHVISION_VERSION"
"$PYTHON_EXE" -m pip install -r training/requirements.txt
"$PYTHON_EXE" training/verify_environment.py --expect-device any

echo
echo "Mac training environment ready."
echo "Activate with:"
echo "  source $VENV_PATH/bin/activate"
