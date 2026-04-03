#!/usr/bin/env bash
set -euo pipefail

echo "[1/7] Updating system packages..."
sudo apt update
sudo apt full-upgrade -y

echo "[2/7] Installing basic dependencies..."
sudo apt install -y git python3-venv python3-opencv python3-gpiozero python3-serial

echo "[3/7] Creating local runtime directories..."
mkdir -p runtime/captures
mkdir -p runtime/inference_records/json
mkdir -p runtime/logs
mkdir -p runtime/experiments
mkdir -p runtime/models
mkdir -p runtime/tmp

echo "[4/7] Creating Python virtual environment if missing..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "[5/7] Activating venv and upgrading pip..."
source .venv/bin/activate
pip install --upgrade pip

echo "[6/7] Installing lightweight repo Python dependencies..."
pip install "Pillow>=10.0"

echo "[7/7] Pi setup complete."
echo "Next:"
echo "  source .venv/bin/activate"
echo "  pip install torch torchvision"
echo "  bash scripts/pi/test_cam.sh"
echo "  python3 scripts/pi/test_leds.py"
