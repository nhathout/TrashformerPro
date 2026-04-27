# TrashformerPro

TrashformerPro is a smart waste-sorting prototype. It uses a Raspberry Pi camera and a trained image classifier to identify one item placed on a controlled plate, then gives category feedback through the web app, LEDs, and buzzer.

The final project implementation includes perception, runtime logging, web-app monitoring, and non-motor hardware feedback. The physical tilting/motor mechanism was planned but is left as future work.

## Demo

Add a screenshot or GIF from the final demo video here:

```text
![TrashformerPro final demo](docs/demo-placeholder.gif)
```

## Current Scope

- Four deployed classes: `plastic`, `paper_cardboard`, `metal_glass`, and `trash_other`
- Transfer-learning image classifier using a torchvision backbone
- Raspberry Pi camera capture and CPU inference
- Empty-plate calibration for simple object-presence checking
- Runtime archive of captures, predictions, JSON records, and event logs
- Web app with upload mode, model status, history, insights, and Pi live monitor
- LED and buzzer feedback for the predicted class

## Not Included In Final Implementation

The motorized tilting mechanism is future work. The repository includes the software structure needed to classify objects and drive user feedback, but it does not complete motor-driver wiring, ESP32 motor firmware, or the mechanical tilt-control loop.

Recommended future motor work:

- choose and wire an appropriate motor driver rather than driving motors from Pi GPIO
- define whether the ESP32 or Raspberry Pi owns motor control
- map each class to a physical bin position
- add limit/position sensing before allowing autonomous motion
- integrate motion only after classification confidence and object staging are stable

## System Overview

- Raspberry Pi 5: camera capture, classifier runtime, LEDs, buzzer, and optional app backend
- Web app: upload classification, history, insights, and live Pi runtime view
- Training machines: Windows GPU, Mac, or BU SCC
- Model checkpoint convention: `models/best.pt`

## Quick Start: Raspberry Pi Demo

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
pip install torch torchvision
```

Confirm a trained checkpoint exists:

```bash
ls -lh models/best.pt
```

Capture the empty plate after the camera and lighting are set:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Run the robot-only loop:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive
```

If using an active buzzer:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode active
```

## Quick Start: Tandem Web-App + HW Demo

Use this mode when the Pi hosts the backend and the web app mirrors the same live runtime that is driving LEDs and the buzzer.

On the Pi:

```bash
cd ~/TrashformerPro
bash scripts/pi/start_tandem_demo.sh
```

From another machine on the same network, open:

```text
http://<pi-ip>:8000
```

Only one process should own the Pi camera at a time. Do not run `scripts/pi/full_system_runner.py` while the app live runtime is active.

## Quick Start: Manual Inference

```bash
source .venv/bin/activate
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu
```

Each run saves:

- the captured image in `runtime/captures/`
- a row in `runtime/inference_records/predictions.csv`
- a JSON record in `runtime/inference_records/json/`

## Training

Windows GPU:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\training\windows\setup_windows_gpu.ps1 -PythonLauncher python3.13.exe
.\training\windows\train_baseline.ps1
```

Mac:

```bash
bash training/mac/setup_mac_training.sh
bash training/mac/train_baseline.sh
```

The best checkpoint from a run is written under `training/runs/<run_name>/best.pt`. Copy the selected checkpoint to `models/best.pt` for Pi deployment.

## Repository Guide

- `apps/trashformer_app/`: React/Vite frontend and FastAPI backend
- `docs/hardware/`: wiring notes for LEDs, buzzer, and ESP32 bring-up
- `inference/pi/`: Pi capture and classification scripts
- `scripts/pi/`: Pi setup, calibration, hardware tests, and runtime launchers
- `training/`: dataset preparation, training scripts, and feedback fine-tuning tools
- `models/best.pt`: deployed classifier checkpoint location

Additional guides:

- `training/README.md`
- `inference/README.md`
- `scripts/pi/README.md`
- `apps/trashformer_app/README.md`
- `docs/hardware/README.md`

## Runtime Artifacts

Runtime captures, logs, prediction records, and training runs are generated locally. These files are useful for final evaluation and later fine-tuning, but they are not required to understand or run the repository.

## Notes

- The classifier assumes one object at a time on a controlled plate.
- The current four-bin setup maps clothes, shoes, and other unsupported items into `trash_other`.
- Empty-plate comparison is a practical prototype heuristic, not full object detection.