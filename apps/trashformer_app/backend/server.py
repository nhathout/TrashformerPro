from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.trashformer_app.backend import main as backend_main

APP_MODULE = "apps.trashformer_app.backend.main"
FRONTEND_DIST_DIR = REPO_ROOT / "apps" / "trashformer_app" / "frontend" / "dist"

app = FastAPI(title="Trashformer App Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_function(module_name: str | None, func_name: str) -> Callable[..., Any]:
    if module_name and module_name != APP_MODULE:
        raise HTTPException(status_code=400, detail=f"Unsupported module '{module_name}'")

    func = getattr(backend_main, func_name, None)
    if func is None or not callable(func):
        raise HTTPException(status_code=404, detail=f"Unknown backend function '{func_name}'")
    return func


def _parse_payload(payload: dict[str, Any]) -> tuple[Callable[..., Any], dict[str, Any]]:
    func_name = payload.get("func")
    if not isinstance(func_name, str) or not func_name:
        raise HTTPException(status_code=400, detail="Missing 'func' in request body")

    args = payload.get("args") or {}
    if not isinstance(args, dict):
        raise HTTPException(status_code=400, detail="'args' must be a JSON object")

    module_name = payload.get("module")
    if module_name is not None and not isinstance(module_name, str):
        raise HTTPException(status_code=400, detail="'module' must be a string")

    return _resolve_function(module_name, func_name), args


def _encode_sse(data: Any) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode("utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/data")
def data(payload: dict[str, Any]) -> JSONResponse:
    func, args = _parse_payload(payload)
    result = func(**args)
    if hasattr(result, "__iter__") and not isinstance(result, (dict, list, str, bytes, tuple)):
        raise HTTPException(status_code=400, detail="Streaming functions must use /data/stream")
    return JSONResponse(result)


@app.post("/data/stream")
def data_stream(payload: dict[str, Any]) -> StreamingResponse:
    func, args = _parse_payload(payload)
    result = func(**args)
    if not hasattr(result, "__iter__") or isinstance(result, (dict, list, str, bytes, tuple)):
        raise HTTPException(status_code=400, detail="Function does not return a stream")

    def event_stream():
        try:
            for chunk in result:
                yield _encode_sse(chunk)
        except Exception as exc:
            yield _encode_sse({"status": "error", "error": str(exc)})

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def root() -> PlainTextResponse:
        return PlainTextResponse(
            "Frontend build not found. Run 'npm run build' in apps/trashformer_app/frontend to serve the app here."
        )


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("TRASHFORMER_HOST", "0.0.0.0")
    uvicorn.run("apps.trashformer_app.backend.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
