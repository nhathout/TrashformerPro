# Pi Runtime Guide

## What Lives Here

- `scripts/pi/setup_pi.sh`: installs Pi-side packages and creates runtime folders
- `scripts/pi/capture_empty_reference.py`: captures the calibrated empty plate image
- `scripts/pi/full_system_runner.py`: robot-only CLI wrapper around the shared Pi runtime
- `scripts/pi/run_hardware_action.py`: one-shot LED/buzzer helper
- `scripts/pi/test_cam.sh`: camera smoke test
- `scripts/pi/test_leds.py`: LED smoke test
- `scripts/pi/test_buzzer.py`: buzzer smoke test
- `scripts/pi/test_esp32_serial.py`: optional ESP32 serial test

## Runtime Modes

TrashformerPro now has one shared Pi runtime state machine with a `2.0 s` stable hold and three supported ways to use it:

1. `Robot-only`
   Run `scripts/pi/full_system_runner.py`. No website required.
2. `App-only`
   Run the website on any machine. Upload/history/insights work without Pi hardware.
3. `Tandem Pi demo`
   Run the app backend on the Pi with the shared runtime already active, and use the web app as a real-time mirror of the same LED / buzzer / classification state.

Important:

- only one live Pi runtime may own the camera at a time
- do not run `full_system_runner.py` while the Pi app backend live runtime is active
- if you want app + hardware together, use the app `Live Monitor` with hardware mirroring enabled

## One-Time Pi Setup

From the repo root on the Pi:

```bash
cd ~/TrashformerPro
bash scripts/pi/setup_pi.sh
```

That prepares:

- `runtime/calibration/`
- `runtime/captures/`
- `runtime/inference_records/`
- `runtime/logs/`

## Starting A New Pi Session After Reboot

From the repo root on the Pi:

```bash
cd ~/TrashformerPro
source .venv/bin/activate
ls -lh models/best.pt
```

If you pulled changes that affect packages or hardware dependencies, rerun:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
```

Recapture `runtime/calibration/empty_plate.jpg` whenever any of these changed:

- camera angle
- camera height
- lighting
- plate position
- background / framing

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Then choose either:

- robot-only CLI runtime from this README
- Pi-hosted app runtime from [apps/trashformer_app/README.md](/Users/noahhathout/Desktop/Work/Grad%20School/SE740/TrashformerPro/apps/trashformer_app/README.md)

For most demos, tandem mode is now the default path.

## Python Usage On The Pi

Use `/usr/bin/python3` for GPIO-facing scripts in `scripts/pi/`.

Reason:

- `setup_pi.sh` installs `gpiozero` and serial tooling for the system Python
- the classifier itself still runs from `.venv/bin/python`

The normal split is:

- hardware entrypoint: `/usr/bin/python3`
- classifier subprocess: `.venv/bin/python`

## Quick Hardware Checks

### Camera

```bash
bash scripts/pi/test_cam.sh
```

### LEDs

```bash
/usr/bin/python3 scripts/pi/test_leds.py --cycles 1 --hold-seconds 1.0
```

Default GPIO map:

- `plastic`: `GPIO17` / physical pin `11`
- `paper_cardboard`: `GPIO27` / physical pin `13`
- `metal_glass`: `GPIO22` / physical pin `15`
- `trash_other`: `GPIO23` / physical pin `16`

### Buzzer

Active buzzer:

```bash
/usr/bin/python3 scripts/pi/test_buzzer.py --mode active
```

Passive piezo buzzer:

```bash
/usr/bin/python3 scripts/pi/test_buzzer.py --mode passive
```

Default buzzer pin:

- `GPIO24` / physical pin `18`

## Blank Reference Calibration

Capture the empty plate with normal lighting and the final framing:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

This creates:

```text
runtime/calibration/empty_plate.jpg
```

The shared runtime uses that image for:

- blank-reference foreground checking
- center-object presence gating
- border-region plate / framing mismatch detection

## Robot-Only Runtime

Run the physical system without the website:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive \
  --stable-hold-seconds 2.0 \
  --standby-reminder-seconds 20 \
  --min-confidence 0.60
```

If you use an active buzzer instead:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode active \
  --stable-hold-seconds 2.0 \
  --standby-reminder-seconds 20 \
  --min-confidence 0.60
```

What the runtime does:

- captures `empty_plate.jpg` during tandem-demo startup, or uses the existing calibration image for robot-only mode
- plays the boot sound and lights all LEDs briefly when hardware outputs are enabled
- captures the latest live frame
- compares it to `empty_plate.jpg` after grayscale + blur preprocessing
- checks for a valid core foreground object in the plate center
- if no core object is found, checks for a border-region plate / framing mismatch
- waits `2.0 s` for the same object to stay stable
- crops around the detected object and classifies with `models/best.pt`
- logs runtime events and archives classification-attempt frames

Runtime states:

- `standby`: empty plate or no object
- `tracking`: object present but still within the `2.0 s` hold window, with all class LEDs lit
- `classified`: confident prediction, with the winning class LED held until the next state change
- `low_confidence` is recorded internally, but the runtime immediately returns to `standby`
- `scene_error`: plate moved, disappeared, or framing changed too much
- `degraded`: camera / classifier / runtime problem, with automatic retry

Low-confidence behavior:

- the classifier still archives the frame and logs the prediction attempt
- LEDs and buzzer return to standby behavior instead of showing a category
- the web app does not show the locked-class popup unless the confidence threshold passed

Useful options:

- `--min-confidence 0.75`
- `--stable-hold-seconds 2.0`
- `--category-hold-seconds 2.0`
- `--standby-reminder-seconds 0`
- `--skip-presence-check`
- `--camera-arg=--timeout --camera-arg=1000`
- `--once`

Deprecated compatibility note:

- `--decision-hold-seconds` still works as an alias for `--category-hold-seconds`
- category LEDs now stay latched until the runtime leaves `classified`, so `--category-hold-seconds` is mostly legacy

## Default Tandem Demo Mode

This is the recommended presentation / demo path because the web app and hardware mirror the same runtime in real time.

Start it on the Pi with:

```bash
cd ~/TrashformerPro
bash scripts/pi/start_tandem_demo.sh
```

That launches:

- the backend server
- the shared Pi runtime
- hardware outputs enabled by default
- an automatic blank-reference capture before the runtime starts

The runtime continues running even if the browser is not open. Live image frames are only encoded and sent when the web app `Live Monitor` is actively polling.

From your Mac, open:

```text
http://<pi-ip>:8000
```

Then use `Live Monitor` as the real-time view of the same runtime that is driving LEDs and buzzer.

## Where Runtime Output Goes

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

Each prediction record includes the checkpoint path and SHA-256 fingerprint used for that inference.

## Copy Captures Back To Your Mac

From your Mac:

```bash
scp <pi-user>@<pi-host>:~/TrashformerPro/runtime/captures/fullrun_locked_<timestamp>.jpg ~/Downloads/
```

Or copy the full runtime data for relabeling / fine-tuning:

```bash
rsync -av <pi-user>@<pi-host>:~/TrashformerPro/runtime/captures/ runtime/captures/
rsync -av <pi-user>@<pi-host>:~/TrashformerPro/runtime/inference_records/ runtime/inference_records/
```

For the relabel + fine-tune loop, see [training/README.md](/Users/noahhathout/Desktop/Work/Grad%20School/SE740/TrashformerPro/training/README.md).
