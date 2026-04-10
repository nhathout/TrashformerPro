# Trashformer App

`apps/trashformer_app` contains a React/Vite frontend and a Python backend that exposes:

- `POST /data` for standard RPC calls
- `POST /data/stream` for streaming classification updates
- `GET /health` for a quick backend sanity check

## Local Run

### Backend

From the repo root:

```bash
python3 -m venv .venv-trashformer
source .venv-trashformer/bin/activate
pip install -r apps/trashformer_app/backend/requirements.txt
python apps/trashformer_app/backend/server.py
```

Optional real-model inference:

- install the extra ML runtime with `pip install -r apps/trashformer_app/backend/requirements-inference.txt`
- place a checkpoint at `runtime/models/best.pt`, or
- set `TRASHFORMER_CHECKPOINT=/absolute/path/to/best.pt`

If no checkpoint is available, the app still works with deterministic demo predictions so the UI can be exercised end to end.

### Frontend with Vite

From `apps/trashformer_app/frontend`:

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

### Frontend with VS Code Live Server

Live Server cannot run the source app directly because the frontend is TypeScript/React and must be built first.

From `apps/trashformer_app/frontend`:

```bash
npm install
npm run build
```

Then serve `apps/trashformer_app/frontend/dist/index.html` with Live Server and keep the backend running on `http://127.0.0.1:8000`.

The frontend auto-detects Live Server and will call the backend on port `8000`.

## Single-Origin Hosting

Build the frontend first:

```bash
cd apps/trashformer_app/frontend
npm install
npm run build
```

Then deploy the repo with a command like:

```bash
pip install -r apps/trashformer_app/backend/requirements.txt
python apps/trashformer_app/backend/server.py
```

If `apps/trashformer_app/frontend/dist` exists, the backend serves the built frontend and API from the same origin, which avoids CORS issues.
