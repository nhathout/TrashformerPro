# Pi Runtime Guide

This folder contains Raspberry Pi setup, calibration, hardware checks, and runtime launch scripts.

## Files

- `setup_pi.sh`: installs Pi-side packages and creates runtime folders
- `capture_empty_reference.py`: captures the calibrated empty-plate image
- `full_system_runner.py`: robot-only CLI runtime
- `start_tandem_demo.sh`: starts the Pi-hosted app and shared runtime
- `run_hardware_action.py`: one-shot LED/buzzer helper
- `test_cam.sh`: camera smoke test
- `test_leds.py`: LED smoke test
- `test_buzzer.py`: buzzer smoke test
- `test_esp32_serial.py`: optional ESP32 serial test

## Runtime Modes

Robot-only:

- run `scripts/pi/full_system_runner.py`
- no website required

App-only:

- run the web app without Pi hardware
- upload, history, and insights still work

Tandem Pi demo:

- run the backend and shared Pi runtime on the Pi
- use the web app as a live view of the same runtime driving LEDs and buzzer

Only one live runtime should own the Pi camera. Do not run `full_system_runner.py` while the app live runtime is active.

## One-Time Setup

```bash
cd ~/TrashformerPro
bash scripts/pi/setup_pi.sh
```

This prepares:

- `runtime/calibration/`
- `runtime/captures/`
- `runtime/inference_records/`
- `runtime/logs/`

## Session Startup After Reboot

```bash
cd ~/TrashformerPro
source .venv/bin/activate
ls -lh models/best.pt
```

Recapture the empty reference when the camera, plate, lighting, or background changes:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

## Python Split On The Pi

Use `/usr/bin/python3` for GPIO-facing scripts in `scripts/pi/`.

Use `.venv/bin/python` for classifier inference.

The full runtime does both:

- hardware entrypoint: `/usr/bin/python3`
- classifier subprocess: `.venv/bin/python`

## Hardware Checks

Camera:

```bash
bash scripts/pi/test_cam.sh
```

LEDs:

```bash
/usr/bin/python3 scripts/pi/test_leds.py --cycles 1 --hold-seconds 1.0
```

Default LED map:

- `plastic`: `GPIO17` / physical pin `11`
- `paper_cardboard`: `GPIO27` / physical pin `13`
- `metal_glass`: `GPIO22` / physical pin `15`
- `trash_other`: `GPIO23` / physical pin `16`

Buzzer:

```bash
/usr/bin/python3 scripts/pi/test_buzzer.py --mode passive
```

Use `--mode active` for an active buzzer.

Default buzzer pin:

- `GPIO24` / physical pin `18`

## Robot-Only Runtime

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive \
  --stable-hold-seconds 2.0 \
  --standby-reminder-seconds 20 \
  --min-confidence 0.60
```

Use `--buzzer-mode active` if needed.

Runtime states:

- `standby`: empty plate or no object
- `tracking`: object is present but still inside the stability window
- `classified`: confident prediction
- `scene_error`: plate, background, or framing changed too much
- `degraded`: camera, classifier, or runtime problem with automatic retry

Useful options:

- `--min-confidence 0.75`
- `--stable-hold-seconds 2.0`
- `--category-hold-seconds 2.0`
- `--standby-reminder-seconds 0`
- `--skip-presence-check`
- `--camera-arg=--timeout --camera-arg=1000`
- `--once`

## Tandem Demo Mode

This is the preferred final demo path when the Pi hosts the app.

```bash
cd ~/TrashformerPro
bash scripts/pi/start_tandem_demo.sh
```

If the buzzer is silent and the hardware uses an active buzzer:

```bash
cd ~/TrashformerPro
TRASHFORMER_RUNTIME_BUZZER_MODE=active bash scripts/pi/start_tandem_demo.sh
```

The launcher starts:

- the backend server
- the shared Pi runtime
- hardware outputs
- an empty-plate calibration capture before runtime startup

From another machine on the same network:

```text
http://<pi-ip>:8000
```

## Runtime Output

Latest live frame:

```text
runtime/captures/live_monitor_latest.jpg
```

Archived classification attempts:

```text
runtime/captures/live_monitor_locked_<timestamp>.jpg
runtime/captures/live_monitor_locked_<timestamp>_full.jpg
```

Prediction records:

```text
runtime/inference_records/predictions.csv
runtime/inference_records/json/
```

Runtime event log:

```text
runtime/logs/full_system_events.jsonl
```

## Copy Captures Back For Review

```bash
rsync -av <pi-user>@<pi-host>:~/TrashformerPro/runtime/captures/ runtime/captures/
rsync -av <pi-user>@<pi-host>:~/TrashformerPro/runtime/inference_records/ runtime/inference_records/
```

For relabeling and fine-tuning, see `training/README.md`.