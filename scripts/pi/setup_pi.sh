#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] Updating system packages..."
sudo apt update
sudo apt full-upgrade -y

echo "[2/6] Installing basic dependencies..."
sudo apt install -y git python3-venv python3-opencv

echo "[3/6] Creating local runtime directories..."
mkdir -p runtime/captures
mkdir -p runtime/logs
mkdir -p runtime/experiments
mkdir -p runtime/tmp

echo "[4/6] Creating Python virtual environment if missing..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "[5/6] Activating venv and upgrading pip..."
source .venv/bin/activate
pip install --upgrade pip

echo "[6/6] Pi setup complete."
echo "Next:"
echo "  source .venv/bin/activate"
echo "  bash scripts/pi/test_camera.sh"