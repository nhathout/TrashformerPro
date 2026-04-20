# Trashformer App

`apps/trashformer_app` contains:

- a React / Vite frontend
- a FastAPI backend
- the Pi live runtime controls used by the `Live Monitor` tab

Backend endpoints:

- `POST /data`
- `POST /data/stream`
- `GET /health`

## What Works Without The Pi

The website is intentionally usable without robot hardware.

These features work on Mac, Linux, or any machine with the backend dependencies:

- upload classification
- model status
- history
- insights

If the backend is not running on a Pi with camera access, the app stays in `Upload / Website Mode Only` and disables `Live Monitor` cleanly.

## What Is Pi-Only

`Live Monitor` depends on the backend host having:

- `rpicam-still`
- a captured `runtime/calibration/empty_plate.jpg`
- a usable checkpoint such as `models/best.pt`

Optional Pi-only hardware features:

- LED output
- buzzer output

## Local App Run

From the repo root:

```bash
python3 -m venv .venv-trashformer
source .venv-trashformer/bin/activate
pip install -r apps/trashformer_app/backend/requirements.txt
python apps/trashformer_app/backend/server.py
```

Optional real-model inference for upload classification:

```bash
pip install -r apps/trashformer_app/backend/requirements-inference.txt
```

Then either:

- put a checkpoint at `models/best.pt`, or
- set `TRASHFORMER_CHECKPOINT=/absolute/path/to/best.pt`

If no checkpoint is available, upload classification still works in deterministic demo mode.

## Frontend Development

From `apps/trashformer_app/frontend`:

```bash
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Single-Origin Build

Build the frontend:

```bash
cd apps/trashformer_app/frontend
npm install
npm run build
cd ../../..
```

Then run the backend:

```bash
source .venv-trashformer/bin/activate
python apps/trashformer_app/backend/server.py
```

If `apps/trashformer_app/frontend/dist` exists, the backend serves the built frontend and API from the same origin.

## Live Monitor Behavior

The app `Live Monitor` now controls a shared Pi runtime instead of running its own separate snapshot logic.

That runtime:

- captures the latest frame from the Pi camera
- performs a blank-reference foreground check against `runtime/calibration/empty_plate.jpg`
- distinguishes:
  - `standby`
  - `tracking`
  - `classified`
  - `low_confidence`
  - `scene_error`
  - `degraded`
- requires a `2.0 s` stable hold before classification
- can optionally mirror the same runtime state to the Pi LEDs and buzzer
- archives locked classification frames into `runtime/captures/`
- writes locked predictions to `runtime/inference_records/predictions.csv`

Important:

- the app can run without the robot
- the robot can run without the app
- if you want app + hardware together, start the runtime from the app and enable hardware mirroring there
- do not run `scripts/pi/full_system_runner.py` at the same time as the app live runtime

## Recommended Pi Demo Flow

Use this when the backend runs on the Pi and you view the app from your Mac.

### On The Pi

```bash
cd ~/TrashformerPro
source .venv/bin/activate
pip install -r apps/trashformer_app/backend/requirements-inference.txt
```

If the frontend has not been built on that Pi yet, or frontend code changed:

```bash
cd apps/trashformer_app/frontend
npm install
npm run build
cd ../../..
```

Confirm the checkpoint:

```bash
ls -lh models/best.pt
```

Capture the blank reference:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Start the backend:

```bash
python apps/trashformer_app/backend/server.py
```

### On Your Mac

Check health:

```bash
curl http://<pi-ip>:8000/health
```

Check model status:

```bash
curl -X POST http://<pi-ip>:8000/data \
  -H "Content-Type: application/json" \
  -d '{"func":"get_model_status","args":{}}'
```

Open:

```text
http://<pi-ip>:8000
```

Inside the app:

1. open `Live Monitor`
2. click `Start`
3. optionally enable `Mirror Pi LEDs + buzzer`

The app backend then owns:

- the Pi camera
- the `2.0 s` stability gate
- classification
- optional LED / buzzer outputs

## Start Another Session After Reboot

On the Pi:

```bash
cd ~/TrashformerPro
source .venv/bin/activate
ls -lh models/best.pt
```

Rebuild the frontend only if it changed:

```bash
cd apps/trashformer_app/frontend
npm install
npm run build
cd ../../..
```

Recapture the blank reference if the camera, lighting, plate, or framing changed:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Start the backend:

```bash
python apps/trashformer_app/backend/server.py
```

On your Mac, hard refresh the browser if the UI does not look current.
