from __future__ import annotations

import base64
import hashlib
import io
import os
import shutil
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_engine import (
    DEFAULT_CAMERA_TIMEOUT_MS,
    DEFAULT_LIVE_CAPTURE_PATH,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_STABLE_HOLD_SECONDS,
    DEFAULT_STANDBY_REMINDER_SECONDS,
    HardwareConfig,
    PiRuntimeEngine,
    PresenceConfig,
    RuntimeConfig,
)
from inference.pi.hardware_outputs import gpio_outputs_supported
from inference.pi.runtime_utils import describe_checkpoint_file, repo_relative, resolve_checkpoint_path

BACKEND_DIR = Path(__file__).resolve().parent
DB_DIR = BACKEND_DIR / "data" / "db"
DB_PATH = DB_DIR / "history.db"
CLASSES = ["plastic", "paper_cardboard", "metal_glass", "trash_other"]
DEFAULT_REFERENCE_PATH = REPO_ROOT / "runtime" / "calibration" / "empty_plate.jpg"
DEFAULT_LIVE_RESIZE = 256
DEFAULT_LIVE_HOLD_SECONDS = DEFAULT_STABLE_HOLD_SECONDS
DEFAULT_LIVE_CAMERA_WIDTH = 1280
DEFAULT_LIVE_CAMERA_HEIGHT = 720
DEFAULT_LIVE_CATEGORY_HOLD_SECONDS = 2.0
DEFAULT_LIVE_STANDBY_REMINDER_SECONDS = DEFAULT_STANDBY_REMINDER_SECONDS
DEFAULT_RUNTIME_CLASSIFIER_PYTHON = Path(sys.executable)

_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, Any] = {}
_RUNTIME_SERVICE_LOCK = threading.Lock()


def _get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            category TEXT,
            confidence REAL,
            inference_time_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _resolve_checkpoint_path() -> Path | None:
    env_value = os.getenv("TRASHFORMER_CHECKPOINT")
    if env_value:
        try:
            return resolve_checkpoint_path(Path(env_value).expanduser())
        except FileNotFoundError:
            return None

    try:
        return resolve_checkpoint_path()
    except FileNotFoundError:
        pass

    run_checkpoints = sorted(
        (REPO_ROOT / "training" / "runs").glob("**/best.pt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return run_checkpoints[0] if run_checkpoints else None


def _get_model_bundle(checkpoint_path: Path) -> dict[str, Any]:
    import torch

    from training.modeling import build_eval_transform, build_model

    global _MODEL_CACHE

    resolved = checkpoint_path.resolve()
    stat = resolved.stat()
    cache_key = f"{resolved}:{stat.st_mtime_ns}:{stat.st_size}"

    with _MODEL_CACHE_LOCK:
        cached_key = _MODEL_CACHE.get("key")
        if cached_key == cache_key:
            return _MODEL_CACHE["bundle"]

        device = torch.device("cpu")
        checkpoint = torch.load(resolved, map_location=device)
        class_names = list(checkpoint["class_names"])
        model_name = checkpoint["model_name"]
        img_size = int(checkpoint.get("img_size", 224))

        model = build_model(model_name, len(class_names), pretrained=False)
        model.load_state_dict(checkpoint["model_state"])
        model.to(device)
        model.eval()

        bundle = {
            "device": device,
            "checkpoint": checkpoint,
            "class_names": class_names,
            "model_name": model_name,
            "img_size": img_size,
            "model": model,
            "transform": build_eval_transform(img_size),
            "file_info": describe_checkpoint_file(resolved),
        }
        _MODEL_CACHE = {
            "key": cache_key,
            "bundle": bundle,
        }
        return bundle


def _classify_with_checkpoint(image: Image.Image, checkpoint_path: Path) -> Dict[str, Any]:
    import torch

    bundle = _get_model_bundle(checkpoint_path)
    input_tensor = bundle["transform"](image).unsqueeze(0).to(bundle["device"])

    with torch.no_grad():
        logits = bundle["model"](input_tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu()

    top_index = int(probabilities.argmax().item())
    confidence = float(probabilities[top_index].item())
    return {
        "category": bundle["class_names"][top_index],
        "confidence": round(confidence, 4),
        "model_source": bundle["file_info"]["checkpoint"],
        "checkpoint_sha256": bundle["file_info"]["checkpoint_sha256"],
        "model_name": bundle["model_name"],
    }


def _classify_with_mock(image_data: bytes) -> Dict[str, Any]:
    img_hash = int(hashlib.md5(image_data).hexdigest(), 16)
    category = CLASSES[img_hash % len(CLASSES)]
    confidence = 0.85 + ((img_hash % 1400) / 10000)
    return {
        "category": category,
        "confidence": round(min(confidence, 0.99), 4),
        "model_source": "mock",
        "checkpoint_sha256": "",
        "model_name": "demo",
    }


def _classify_image(image: Image.Image, image_data: bytes) -> Dict[str, Any]:
    checkpoint_path = _resolve_checkpoint_path()
    if checkpoint_path is None:
        return _classify_with_mock(image_data)

    return _classify_with_checkpoint(image, checkpoint_path)


def _insert_prediction(filename: str, category: str, confidence: float, inference_time_ms: float) -> None:
    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO predictions (filename, category, confidence, inference_time_ms)
            VALUES (?, ?, ?, ?)
            """,
            (filename, category, confidence, inference_time_ms),
        )
        conn.commit()
    finally:
        conn.close()


def _current_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackendRuntimeService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._engine: PiRuntimeEngine | None = None
        self._thread: threading.Thread | None = None
        self._config: RuntimeConfig | None = None

    def _build_idle_snapshot(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": _current_utc_iso(),
            "active": False,
            "state": "standby",
            "status": "standby",
            "status_message": "Runtime is idle.",
            "error": "",
            "image_b64": "",
            "image_path": None,
            "prediction": None,
            "presence": None,
            "tracking": {
                "stable_for_seconds": 0.0,
                "required_hold_seconds": float(DEFAULT_LIVE_HOLD_SECONDS),
                "object_id": None,
            },
            "decision": None,
            "confidence_passed": False,
            "classification_triggered": False,
            "classification_event_id": None,
            "saved_capture_path": None,
            "hardware": {
                "enabled": False,
                "buzzer_mode": "passive",
                "action": "disabled",
                "error": "",
            },
            "capture_time_ms": 0.0,
        }

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            engine = self._engine
            thread = self._thread

        if engine is None:
            return self._build_idle_snapshot()

        snapshot = engine.get_snapshot()
        if thread is not None and not thread.is_alive() and snapshot.get("active"):
            snapshot["active"] = False
        return snapshot

    def start(self, config: RuntimeConfig) -> Dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._config == config:
                return self._engine.get_snapshot() if self._engine is not None else self._build_idle_snapshot()

        self.stop(clear_outputs=True)

        engine = PiRuntimeEngine(config, prediction_callback=_record_runtime_prediction)
        thread = threading.Thread(target=engine.run_forever, daemon=True, name="trashformer-pi-runtime")

        with self._lock:
            self._config = config
            self._engine = engine
            self._thread = thread

        thread.start()
        time.sleep(0.1)
        return engine.get_snapshot()

    def stop(self, clear_outputs: bool = True) -> Dict[str, Any]:
        with self._lock:
            engine = self._engine
            thread = self._thread

        if engine is not None:
            engine.stop()
        if thread is not None:
            thread.join(timeout=5.0)

        snapshot = engine.get_snapshot() if engine is not None else self._build_idle_snapshot()
        if clear_outputs and snapshot.get("hardware", {}).get("enabled"):
            snapshot["status_message"] = "Runtime stopped and outputs cleared."

        with self._lock:
            self._engine = None
            self._thread = None
            self._config = None

        snapshot["active"] = False
        return snapshot


_RUNTIME_SERVICE = BackendRuntimeService()


def _record_runtime_prediction(payload: Dict[str, Any]) -> None:
    prediction = payload["predictions"][0]
    _insert_prediction(
        Path(str(payload["image"])).name,
        prediction["class_name"],
        float(prediction["confidence"]),
        float(payload.get("inference_time_ms", 0.0)),
    )


def _snapshot_with_optional_image(snapshot: Dict[str, Any], include_image: bool) -> Dict[str, Any]:
    enriched = dict(snapshot)
    image_path = enriched.get("image_path")
    if not include_image or not image_path:
        enriched["image_b64"] = ""
        return enriched

    resolved = REPO_ROOT / str(image_path)
    try:
        image_data = resolved.read_bytes()
    except OSError:
        enriched["image_b64"] = ""
        enriched["error"] = enriched.get("error") or f"Latest runtime frame is unavailable: {resolved}"
        return enriched

    enriched["image_b64"] = f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('ascii')}"
    return enriched


def _build_runtime_config(**args: Any) -> RuntimeConfig:
    default_presence = PresenceConfig()
    camera_width = int(args.get("camera_width", DEFAULT_LIVE_CAMERA_WIDTH))
    camera_height = int(args.get("camera_height", DEFAULT_LIVE_CAMERA_HEIGHT))
    camera_timeout_ms = int(args.get("camera_timeout_ms", DEFAULT_CAMERA_TIMEOUT_MS))
    extra_camera_args = [str(value) for value in args.get("camera_args", [])]
    camera_args = (
        "--width",
        str(camera_width),
        "--height",
        str(camera_height),
        "--timeout",
        str(camera_timeout_ms),
        *extra_camera_args,
    )

    classifier_python = Path(str(args.get("classifier_python", DEFAULT_RUNTIME_CLASSIFIER_PYTHON)))
    drive_outputs = bool(args.get("drive_outputs", False))
    hardware_buzzer_mode = str(args.get("hardware_buzzer_mode", "passive"))

    return RuntimeConfig(
        checkpoint_path=_resolve_checkpoint_path(),
        classifier_python=classifier_python,
        classifier_device=str(args.get("classifier_device", "cpu")),
        top_k=int(args.get("top_k", 4)),
        min_confidence=float(args.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
        capture_prefix="live_monitor",
        latest_capture_path=Path(str(args.get("latest_capture_path", DEFAULT_LIVE_CAPTURE_PATH))),
        camera_args=tuple(camera_args),
        empty_reference=Path(str(args.get("empty_reference", DEFAULT_REFERENCE_PATH))),
        skip_presence_check=bool(args.get("skip_presence_check", False)),
        presence=PresenceConfig(
            resize=int(args.get("presence_resize", DEFAULT_LIVE_RESIZE)),
            pixel_threshold=int(args.get("presence_pixel_threshold", default_presence.pixel_threshold)),
            ratio_threshold=float(args.get("presence_ratio_threshold", default_presence.ratio_threshold)),
            mean_threshold=float(args.get("presence_mean_threshold", default_presence.mean_threshold)),
            scene_error_border_fraction=float(
                args.get("scene_error_border_fraction", default_presence.scene_error_border_fraction)
            ),
            scene_error_ratio_threshold=float(
                args.get("scene_error_ratio_threshold", default_presence.scene_error_ratio_threshold)
            ),
            scene_error_mean_threshold=float(
                args.get("scene_error_mean_threshold", default_presence.scene_error_mean_threshold)
            ),
        ),
        loop_interval=float(args.get("loop_interval", 1.0)),
        stable_hold_seconds=float(args.get("stable_hold_seconds", DEFAULT_LIVE_HOLD_SECONDS)),
        hardware=HardwareConfig(
            enabled=drive_outputs,
            buzzer_mode=hardware_buzzer_mode,
            standby_reminder_seconds=float(
                args.get("standby_reminder_seconds", DEFAULT_LIVE_STANDBY_REMINDER_SECONDS)
            ),
            category_hold_seconds=float(
                args.get("category_hold_seconds", DEFAULT_LIVE_CATEGORY_HOLD_SECONDS)
            ),
            alert_cycles=int(args.get("alert_cycles", 3)),
            alert_cycle_seconds=float(args.get("alert_cycle_seconds", 1.0)),
        ),
        log_path=Path(str(args.get("log_path", "runtime/logs/app_runtime_events.jsonl"))),
    )


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_default_runtime_start_args() -> Dict[str, Any]:
    return {
        "stable_hold_seconds": float(os.getenv("TRASHFORMER_RUNTIME_STABLE_HOLD_SECONDS", str(DEFAULT_LIVE_HOLD_SECONDS))),
        "camera_width": int(os.getenv("TRASHFORMER_RUNTIME_CAMERA_WIDTH", str(DEFAULT_LIVE_CAMERA_WIDTH))),
        "camera_height": int(os.getenv("TRASHFORMER_RUNTIME_CAMERA_HEIGHT", str(DEFAULT_LIVE_CAMERA_HEIGHT))),
        "camera_timeout_ms": int(os.getenv("TRASHFORMER_RUNTIME_CAMERA_TIMEOUT_MS", str(DEFAULT_CAMERA_TIMEOUT_MS))),
        "drive_outputs": _env_flag("TRASHFORMER_RUNTIME_DRIVE_OUTPUTS", default=True),
        "hardware_buzzer_mode": os.getenv("TRASHFORMER_RUNTIME_BUZZER_MODE", "passive"),
        "standby_reminder_seconds": float(
            os.getenv("TRASHFORMER_RUNTIME_STANDBY_REMINDER_SECONDS", str(DEFAULT_LIVE_STANDBY_REMINDER_SECONDS))
        ),
        "category_hold_seconds": float(
            os.getenv("TRASHFORMER_RUNTIME_CATEGORY_HOLD_SECONDS", str(DEFAULT_LIVE_CATEGORY_HOLD_SECONDS))
        ),
        "min_confidence": float(os.getenv("TRASHFORMER_RUNTIME_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE))),
        "include_image": False,
    }


def _detect_raspberry_pi_model() -> str:
    model_path = Path("/sys/firmware/devicetree/base/model")
    if not model_path.exists():
        return ""
    try:
        return model_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "").strip()
    except OSError:
        return ""


def get_runtime_capabilities() -> Dict[str, Any]:
    pi_model = _detect_raspberry_pi_model()
    is_raspberry_pi = bool(pi_model)
    camera_command = shutil.which("rpicam-still")
    camera_available = camera_command is not None

    if camera_available:
        camera_reason = "Camera capture command is available on this backend."
    else:
        camera_reason = (
            "Live Monitor requires camera capture on the backend host. "
            "This backend does not have `rpicam-still`, so upload-based classification is the portable mode."
        )

    hardware_outputs_available = is_raspberry_pi and gpio_outputs_supported()
    if hardware_outputs_available:
        hardware_reason = "GPIO output helpers are available on this Raspberry Pi backend."
    else:
        hardware_reason = (
            "LED and buzzer control are only available when the backend runs on the Raspberry Pi with GPIO support."
        )

    live_monitor_supported = camera_available
    live_monitor_reason = (
        "Live Monitor is available."
        if live_monitor_supported
        else "Live Monitor is unavailable on this backend because camera capture is not configured here."
    )

    return {
        "host": {
            "is_raspberry_pi": is_raspberry_pi,
            "pi_model": pi_model or "",
            "platform": sys.platform,
        },
        "camera_available": camera_available,
        "camera_reason": camera_reason,
        "camera_command": camera_command or "",
        "hardware_outputs_available": hardware_outputs_available,
        "hardware_outputs_reason": hardware_reason,
        "live_monitor_supported": live_monitor_supported,
        "live_monitor_reason": live_monitor_reason,
        "checked_at_utc": _current_utc_iso(),
    }


def get_model_status() -> Dict[str, Any]:
    checkpoint_path = _resolve_checkpoint_path()
    if checkpoint_path is None:
        return {
            "ready": False,
            "using_mock": True,
            "mode": "mock",
            "message": "No checkpoint found. The upload UI would fall back to deterministic demo predictions.",
            "checkpoint_path": None,
            "checkpoint_sha256": None,
            "model_name": None,
            "class_names": [],
            "error": "",
            "checked_at_utc": _current_utc_iso(),
        }

    try:
        bundle = _get_model_bundle(checkpoint_path)
    except Exception as exc:
        return {
            "ready": False,
            "using_mock": False,
            "mode": "checkpoint_error",
            "message": "Checkpoint was found but could not be loaded.",
            "checkpoint_path": repo_relative(checkpoint_path),
            "checkpoint_sha256": None,
            "model_name": None,
            "class_names": [],
            "error": str(exc),
            "checked_at_utc": _current_utc_iso(),
        }

    return {
        "ready": True,
        "using_mock": False,
        "mode": "checkpoint",
        "message": "Real checkpoint loaded successfully.",
        "checkpoint_path": bundle["file_info"]["checkpoint"],
        "checkpoint_sha256": bundle["file_info"]["checkpoint_sha256"],
        "model_name": bundle["model_name"],
        "class_names": bundle["class_names"],
        "error": "",
        "checked_at_utc": _current_utc_iso(),
    }


def start_runtime(**args) -> Dict[str, Any]:
    include_image = bool(args.get("include_image", False))
    runtime_capabilities = get_runtime_capabilities()
    model_status = get_model_status()

    if not runtime_capabilities["live_monitor_supported"]:
        snapshot = _RUNTIME_SERVICE.get_snapshot()
        snapshot.update(
            {
                "active": False,
                "state": "degraded",
                "status": "degraded",
                "status_message": "Live runtime is unavailable on this backend.",
                "error": runtime_capabilities["live_monitor_reason"],
                "runtime_capabilities": runtime_capabilities,
                "model_status": model_status,
            }
        )
        return _snapshot_with_optional_image(snapshot, include_image)

    if not model_status["ready"]:
        snapshot = _RUNTIME_SERVICE.get_snapshot()
        snapshot.update(
            {
                "active": False,
                "state": "degraded",
                "status": "degraded",
                "status_message": "Model is not ready for live runtime.",
                "error": model_status["message"] if not model_status["error"] else model_status["error"],
                "runtime_capabilities": runtime_capabilities,
                "model_status": model_status,
            }
        )
        return _snapshot_with_optional_image(snapshot, include_image)

    config = _build_runtime_config(**args)
    snapshot = _RUNTIME_SERVICE.start(config)
    snapshot["runtime_capabilities"] = runtime_capabilities
    snapshot["model_status"] = model_status
    return _snapshot_with_optional_image(snapshot, include_image)


def stop_runtime(clear_outputs: bool = True) -> Dict[str, Any]:
    snapshot = _RUNTIME_SERVICE.stop(clear_outputs=clear_outputs)
    snapshot["runtime_capabilities"] = get_runtime_capabilities()
    snapshot["model_status"] = get_model_status()
    return snapshot


def get_runtime_snapshot(include_image: bool = False) -> Dict[str, Any]:
    snapshot = _RUNTIME_SERVICE.get_snapshot()
    snapshot["runtime_capabilities"] = get_runtime_capabilities()
    snapshot["model_status"] = get_model_status()
    return _snapshot_with_optional_image(snapshot, include_image)


def classify_image_streaming(**args) -> Generator:
    image_b64 = args.get("image_b64", "")
    filename = args.get("filename", "unknown.jpg")

    print(f"[BACKEND_START] classify_image_streaming for {filename}")

    try:
        yield {"status": "processing", "progress": 10, "message": "Decoding image..."}

        header, encoded = image_b64.split(",", 1) if "," in image_b64 else (None, image_b64)
        image_data = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")

        yield {"status": "processing", "progress": 30, "message": "Preprocessing image..."}

        start_time = time.time()
        model_status = get_model_status()
        if model_status["ready"]:
            yield {"status": "processing", "progress": 60, "message": "Running checkpoint inference..."}
        else:
            yield {"status": "processing", "progress": 60, "message": model_status["message"]}

        prediction = _classify_image(image, image_data)
        if prediction["model_source"] == "mock":
            time.sleep(0.35)

        inference_time_ms = (time.time() - start_time) * 1000
        result = {
            "category": prediction["category"],
            "confidence": prediction["confidence"],
            "inference_time_ms": round(inference_time_ms, 2),
            "model_source": prediction["model_source"],
            "checkpoint_sha256": prediction["checkpoint_sha256"],
            "model_name": prediction["model_name"],
        }

        yield {"status": "processing", "progress": 80, "message": "Logging to database..."}

        _insert_prediction(filename, result["category"], result["confidence"], inference_time_ms)

        print(f"[BACKEND_SUCCESS] classify_image_streaming complete: {result['category']}")
        yield {"status": "success", "progress": 100, "result": result}

    except Exception as exc:
        print(f"[BACKEND_ERROR] classify_image_streaming failed: {str(exc)}")
        yield {"status": "error", "progress": 0, "error": str(exc)}


def reset_live_monitor_state(clear_outputs: bool = False) -> Dict[str, Any]:
    return stop_runtime(clear_outputs=clear_outputs)


def get_live_monitor_snapshot(**args) -> Dict[str, Any]:
    return get_runtime_snapshot()


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    print(f"[BACKEND_START] get_history with limit={limit}")
    conn = _get_db()
    try:
        rows = conn.execute(
            """
            SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = [dict(row) for row in rows]
        print(f"[BACKEND_SUCCESS] get_history returned {len(result)} records")
        return result
    except Exception as exc:
        print(f"[BACKEND_ERROR] get_history failed: {str(exc)}")
        raise
    finally:
        conn.close()


def get_stats() -> Dict[str, Any]:
    print("[BACKEND_START] get_stats")
    conn = _get_db()
    try:
        total_count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

        category_rows = conn.execute(
            """
            SELECT category, COUNT(*) as count FROM predictions GROUP BY category
            """
        ).fetchall()

        category_counts = {c: 0 for c in CLASSES}
        for row in category_rows:
            category_counts[row["category"]] = row["count"]

        avg_inference_time = conn.execute("SELECT AVG(inference_time_ms) FROM predictions").fetchone()[0] or 0.0
        result = {
            "total_count": total_count,
            "category_counts": category_counts,
            "avg_inference_time": round(avg_inference_time, 2),
        }
        print(f"[BACKEND_SUCCESS] get_stats: total={total_count}")
        return result
    except Exception as exc:
        print(f"[BACKEND_ERROR] get_stats failed: {str(exc)}")
        raise
    finally:
        conn.close()


def clear_history() -> Dict[str, bool]:
    print("[BACKEND_START] clear_history")
    conn = _get_db()
    try:
        conn.execute("DELETE FROM predictions")
        conn.commit()
        print("[BACKEND_SUCCESS] history cleared")
        return {"success": True}
    except Exception as exc:
        print(f"[BACKEND_ERROR] clear_history failed: {str(exc)}")
        raise
    finally:
        conn.close()
