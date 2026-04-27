# Trashformer App

`apps/trashformer_app` contains the web interface for TrashformerPro:

- React / Vite frontend
- FastAPI backend
- upload classification
- model status, history, and insights
- Pi `Live Monitor` for the shared runtime

## Backend Endpoints

- `POST /data`
- `POST /data/stream`
- `GET /health`

## What Works Without The Pi

These features work on a normal laptop or desktop when the backend dependencies are installed:

- upload classification
- model status
- history
- insights

If the backend is not running on a Pi with camera access, the app stays in website-only mode and disables `Live Monitor`.

## Pi-Only Features

`Live Monitor` depends on the backend host having:

- `rpicam-still`
- `runtime/calibration/empty_plate.jpg`
- a checkpoint such as `models/best.pt`

Optional Pi hardware outputs:

- LEDs
- buzzer

The motorized tilt mechanism is not part of the final app behavior. It is future work after motor hardware and safety checks are added.

## Local Backend

From the repo root:

```bash
python3 -m venv .venv-trashformer
source .venv-trashformer/bin/activate
pip install -r apps/trashformer_app/backend/requirements.txt
python apps/trashformer_app/backend/server.py
```

Optional real-model inference for uploads:

```bash
pip install -r apps/trashformer_app/backend/requirements-inference.txt
```

Then either place a checkpoint at `models/best.pt` or set:

```bash
export TRASHFORMER_CHECKPOINT=/absolute/path/to/best.pt
```

If no checkpoint is available, upload classification still runs in deterministic demo mode.

## Frontend Development

```bash
cd apps/trashformer_app/frontend
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

Run the backend:

```bash
source .venv-trashformer/bin/activate
python apps/trashformer_app/backend/server.py
```

If `apps/trashformer_app/frontend/dist` exists, the backend serves the frontend and API from the same origin.

## Live Monitor Behavior

The `Live Monitor` uses the same Pi runtime state machine as `scripts/pi/full_system_runner.py`.

The runtime:

- captures or uses an empty-plate reference
- captures live camera frames
- checks for a staged foreground object
- waits for the object to remain stable
- classifies the cropped object
- optionally mirrors state to Pi LEDs and buzzer
- archives classification-attempt frames
- writes prediction records to `runtime/inference_records/predictions.csv`

Runtime states shown by the app:

- `standby`
- `tracking`
- `classified`
- `scene_error`
- `degraded`

Only one runtime should own the Pi camera. Do not run `scripts/pi/full_system_runner.py` while the app live runtime is active.

## Recommended Pi Demo

On the Pi:

```bash
cd ~/TrashformerPro
source .venv/bin/activate
pip install -r apps/trashformer_app/backend/requirements-inference.txt
```

Build the frontend if needed:

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

Start tandem mode:

```bash
bash scripts/pi/start_tandem_demo.sh
```

If the buzzer hardware uses active mode:

```bash
TRASHFORMER_RUNTIME_BUZZER_MODE=active bash scripts/pi/start_tandem_demo.sh
```

From another machine on the same network:

```text
http://<pi-ip>:8000
```

Health check:

```bash
curl http://<pi-ip>:8000/health
```

## Session Restart

After a Pi reboot:

```bash
cd ~/TrashformerPro
source .venv/bin/activate
ls -lh models/best.pt
```

Recapture the blank reference if camera, lighting, plate, or framing changed:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Start:

```bash
bash scripts/pi/start_tandem_demo.sh
```