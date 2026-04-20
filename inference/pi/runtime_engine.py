from __future__ import annotations

import copy
import fcntl
import hashlib
import io
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.hardware_outputs import HardwareController, gpio_outputs_supported
from inference.pi.runtime_utils import (
    CAPTURES_DIR,
    ensure_runtime_dirs,
    repo_relative,
    resolve_checkpoint_path,
    resolve_repo_path,
)
from scripts.pi.hardware_config import BUZZER_GPIO_PIN

DEFAULT_REFERENCE_PATH = Path("runtime/calibration/empty_plate.jpg")
DEFAULT_LOG_PATH = Path("runtime/logs/pi_runtime_events.jsonl")
DEFAULT_LOCK_PATH = Path("runtime/locks/pi_runtime.lock")
DEFAULT_CLASSIFIER_PYTHON = Path(".venv/bin/python")
DEFAULT_LIVE_CAPTURE_PATH = Path("runtime/captures/live_monitor_latest.jpg")
DEFAULT_ROBOT_CAPTURE_PATH = Path("runtime/captures/fullrun_latest.jpg")
DEFAULT_STABLE_HOLD_SECONDS = 2.0
DEFAULT_LOOP_INTERVAL = 1.0
DEFAULT_CATEGORY_HOLD_SECONDS = 2.0
DEFAULT_STANDBY_REMINDER_SECONDS = 20.0
DEFAULT_MIN_CONFIDENCE = 0.60
DEFAULT_CAMERA_TIMEOUT_MS = 1000
CLASSIFICATION_IOU_THRESHOLD = 0.45


class RuntimeConfigError(RuntimeError):
    pass


class RuntimeLockError(RuntimeError):
    pass


@dataclass(frozen=True)
class PresenceConfig:
    resize: int = 256
    pixel_threshold: int = 16
    ratio_threshold: float = 0.01
    mean_threshold: float = 6.0
    scene_error_border_fraction: float = 0.18
    scene_error_ratio_threshold: float = 0.18
    scene_error_mean_threshold: float = 18.0


@dataclass(frozen=True)
class HardwareConfig:
    enabled: bool = True
    buzzer_mode: str = "passive"
    buzzer_pin: int = BUZZER_GPIO_PIN
    standby_reminder_seconds: float = DEFAULT_STANDBY_REMINDER_SECONDS
    category_hold_seconds: float = DEFAULT_CATEGORY_HOLD_SECONDS
    alert_cycles: int = 3
    alert_cycle_seconds: float = 1.0


@dataclass(frozen=True)
class RuntimeConfig:
    checkpoint_path: Path | None = None
    classifier_python: Path = DEFAULT_CLASSIFIER_PYTHON
    classifier_device: str = "cpu"
    top_k: int = 4
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    capture_prefix: str = "runtime"
    latest_capture_path: Path = DEFAULT_LIVE_CAPTURE_PATH
    camera_args: tuple[str, ...] = ()
    empty_reference: Path = DEFAULT_REFERENCE_PATH
    skip_presence_check: bool = False
    presence: PresenceConfig = field(default_factory=PresenceConfig)
    loop_interval: float = DEFAULT_LOOP_INTERVAL
    stable_hold_seconds: float = DEFAULT_STABLE_HOLD_SECONDS
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    log_path: Path = DEFAULT_LOG_PATH
    once: bool = False
    lock_path: Path = DEFAULT_LOCK_PATH
    startup_probe_classifier: bool = True


@dataclass
class PresenceAnalysis:
    has_core_foreground: bool
    reference_scene_error: bool
    object_too_close: bool
    mean_diff: float
    changed_ratio: float
    core_mean_diff: float
    core_changed_ratio: float
    border_mean_diff: float
    border_changed_ratio: float
    bbox_area_ratio: float
    bbox_fill_ratio: float
    bbox_pixels: tuple[int, int, int, int] | None
    bbox: dict[str, float] | None
    analysis_width: int
    analysis_height: int
    pixel_threshold: int
    ratio_threshold: float
    mean_threshold: float
    scene_error_border_fraction: float
    scene_error_ratio_threshold: float
    scene_error_mean_threshold: float

    def to_snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("bbox_pixels", None)
        return payload


@dataclass
class PredictionEvent:
    event_id: str
    object_id: str
    archived_image_path: str
    result: dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_bbox(
    bbox: tuple[int, int, int, int] | None,
    *,
    width: int,
    height: int,
) -> dict[str, float] | None:
    if bbox is None:
        return None

    x0, y0, x1, y1 = bbox
    return {
        "left_pct": round((x0 / width) * 100.0, 2),
        "top_pct": round((y0 / height) * 100.0, 2),
        "width_pct": round(((x1 - x0 + 1) / width) * 100.0, 2),
        "height_pct": round(((y1 - y0 + 1) / height) * 100.0, 2),
    }


def _bbox_iou(box_a: tuple[int, int, int, int] | None, box_b: tuple[int, int, int, int] | None) -> float:
    if box_a is None or box_b is None:
        return 0.0

    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    if inter_x1 < inter_x0 or inter_y1 < inter_y0:
        return 0.0

    intersection = (inter_x1 - inter_x0 + 1) * (inter_y1 - inter_y0 + 1)
    area_a = (ax1 - ax0 + 1) * (ay1 - ay0 + 1)
    area_b = (bx1 - bx0 + 1) * (by1 - by0 + 1)
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _extract_bbox(mask: np.ndarray, border_pixels: int) -> tuple[int, int, int, int] | None:
    core_mask = mask.copy()
    if border_pixels > 0:
        core_mask[:border_pixels, :] = False
        core_mask[-border_pixels:, :] = False
        core_mask[:, :border_pixels] = False
        core_mask[:, -border_pixels:] = False

    ys, xs = np.where(core_mask)
    if ys.size == 0 or xs.size == 0:
        return None

    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    width = bbox[2] - bbox[0] + 1
    height = bbox[3] - bbox[1] + 1
    if width * height < 25:
        return None
    return bbox


def _analysis_arrays(image: Image.Image, reference_path: Path, resize: int) -> tuple[np.ndarray, np.ndarray, int, int]:
    original_width, original_height = image.size
    if original_width >= original_height:
        analysis_width = resize
        analysis_height = max(int(resize * (original_height / original_width)), 1)
    else:
        analysis_height = resize
        analysis_width = max(int(resize * (original_width / original_height)), 1)

    target_size = (analysis_width, analysis_height)
    reference = (
        Image.open(reference_path)
        .convert("L")
        .filter(ImageFilter.GaussianBlur(radius=2))
        .resize(target_size)
    )
    current = image.convert("L").filter(ImageFilter.GaussianBlur(radius=2)).resize(target_size)
    return (
        np.asarray(reference, dtype=np.int16),
        np.asarray(current, dtype=np.int16),
        analysis_width,
        analysis_height,
    )


def _map_bbox_to_image(
    bbox: tuple[int, int, int, int],
    *,
    analysis_width: int,
    analysis_height: int,
    image_width: int,
    image_height: int,
    padding_ratio: float = 0.12,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    scale_x = image_width / analysis_width
    scale_y = image_height / analysis_height

    left = int(x0 * scale_x)
    top = int(y0 * scale_y)
    right = int((x1 + 1) * scale_x) - 1
    bottom = int((y1 + 1) * scale_y) - 1

    width = max(right - left + 1, 1)
    height = max(bottom - top + 1, 1)
    pad_x = max(int(width * padding_ratio), 6)
    pad_y = max(int(height * padding_ratio), 6)

    left = max(left - pad_x, 0)
    top = max(top - pad_y, 0)
    right = min(right + pad_x, image_width - 1)
    bottom = min(bottom + pad_y, image_height - 1)
    return left, top, right, bottom


def _crop_image_for_presence(image: Image.Image, presence: PresenceAnalysis | None) -> Image.Image:
    if presence is None or presence.bbox_pixels is None:
        return image.copy()

    left, top, right, bottom = _map_bbox_to_image(
        presence.bbox_pixels,
        analysis_width=presence.analysis_width,
        analysis_height=presence.analysis_height,
        image_width=image.width,
        image_height=image.height,
    )
    return image.crop((left, top, right + 1, bottom + 1)).copy()


def analyze_frame_against_reference(
    image: Image.Image,
    *,
    reference_path: Path,
    presence: PresenceConfig,
) -> PresenceAnalysis:
    reference, current, analysis_width, analysis_height = _analysis_arrays(image, reference_path, presence.resize)
    difference = np.abs(reference - current)
    changed_mask = difference >= presence.pixel_threshold
    mean_diff = float(difference.mean())
    changed_ratio = float(changed_mask.mean())

    border_pixels = max(int(min(analysis_width, analysis_height) * presence.scene_error_border_fraction), 1)
    border_mask = np.zeros_like(changed_mask, dtype=bool)
    border_mask[:border_pixels, :] = True
    border_mask[-border_pixels:, :] = True
    border_mask[:, :border_pixels] = True
    border_mask[:, -border_pixels:] = True

    border_mean_diff = float(difference[border_mask].mean())
    border_changed_ratio = float(changed_mask[border_mask].mean())
    core_region_mask = ~border_mask
    core_mean_diff = float(difference[core_region_mask].mean())
    core_changed_ratio = float(changed_mask[core_region_mask].mean())
    bbox_pixels = _extract_bbox(changed_mask, border_pixels)
    bbox_area_ratio = 0.0
    bbox_fill_ratio = 0.0
    if bbox_pixels is not None:
        x0, y0, x1, y1 = bbox_pixels
        bbox_area = float((x1 - x0 + 1) * (y1 - y0 + 1))
        bbox_area_ratio = bbox_area / float(analysis_width * analysis_height)
        bbox_fill_ratio = float(changed_mask[y0 : y1 + 1, x0 : x1 + 1].mean())

    has_core_candidate = (
        bbox_pixels is not None
        and bbox_fill_ratio >= 0.15
        and bbox_area_ratio >= 0.002
    )
    has_core_foreground = has_core_candidate and (
        core_changed_ratio >= max(presence.ratio_threshold * 0.35, 0.004)
        or core_mean_diff >= max(presence.mean_threshold * 0.5, 4.0)
        or bbox_area_ratio >= 0.01
    )
    object_too_close = has_core_foreground and (
        bbox_area_ratio >= 0.40
        and border_changed_ratio >= max(presence.scene_error_ratio_threshold * 0.75, 0.12)
    )
    reference_scene_error = (
        object_too_close
        or (
            not has_core_foreground
            and border_changed_ratio >= presence.scene_error_ratio_threshold
            and border_mean_diff >= presence.scene_error_mean_threshold
        )
    )

    return PresenceAnalysis(
        has_core_foreground=has_core_foreground,
        reference_scene_error=reference_scene_error,
        object_too_close=object_too_close,
        mean_diff=round(mean_diff, 2),
        changed_ratio=round(changed_ratio, 4),
        core_mean_diff=round(core_mean_diff, 2),
        core_changed_ratio=round(core_changed_ratio, 4),
        border_mean_diff=round(border_mean_diff, 2),
        border_changed_ratio=round(border_changed_ratio, 4),
        bbox_area_ratio=round(bbox_area_ratio, 4),
        bbox_fill_ratio=round(bbox_fill_ratio, 4),
        bbox_pixels=bbox_pixels,
        bbox=_normalize_bbox(bbox_pixels, width=analysis_width, height=analysis_height),
        analysis_width=analysis_width,
        analysis_height=analysis_height,
        pixel_threshold=presence.pixel_threshold,
        ratio_threshold=presence.ratio_threshold,
        mean_threshold=presence.mean_threshold,
        scene_error_border_fraction=presence.scene_error_border_fraction,
        scene_error_ratio_threshold=presence.scene_error_ratio_threshold,
        scene_error_mean_threshold=presence.scene_error_mean_threshold,
    )


class PiRuntimeEngine:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        prediction_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self.prediction_callback = prediction_callback
        self._snapshot_lock = threading.Lock()
        self._snapshot: dict[str, Any] = self._build_idle_snapshot()
        self._stop_event: threading.Event | None = None
        self._lock_handle: io.TextIOWrapper | None = None
        self._hardware: HardwareController | None = None
        self._hardware_error = ""
        self._last_output_state = "idle"
        self._last_output_object_id: str | None = None
        self._object_started_at: float | None = None
        self._last_bbox: tuple[int, int, int, int] | None = None
        self._last_object_id: str | None = None
        self._last_prediction: PredictionEvent | None = None
        self._last_error = ""
        self._capture_failures = 0
        self._last_console_state: str | None = None
        self._last_console_event_id: str | None = None

    def _build_idle_snapshot(self) -> dict[str, Any]:
        return {
            "timestamp_utc": _utc_now_iso(),
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
                "required_hold_seconds": float(self.config.stable_hold_seconds),
                "object_id": None,
            },
            "decision": None,
            "confidence_passed": False,
            "classification_triggered": False,
            "classification_event_id": None,
            "saved_capture_path": None,
            "hardware": self._hardware_snapshot(enabled=False, action="disabled", error=""),
            "capture_time_ms": 0.0,
        }

    def _hardware_snapshot(self, *, enabled: bool, action: str, error: str) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "buzzer_mode": self.config.hardware.buzzer_mode,
            "action": action,
            "error": error,
        }

    def get_snapshot(self) -> dict[str, Any]:
        with self._snapshot_lock:
            return copy.deepcopy(self._snapshot)

    def _set_snapshot(self, **updates: Any) -> None:
        with self._snapshot_lock:
            snapshot = dict(self._snapshot)
            snapshot.update(updates)
            snapshot["timestamp_utc"] = _utc_now_iso()
            self._snapshot = snapshot

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        self._stop_event = stop_event or threading.Event()
        ensure_runtime_dirs()
        self._set_snapshot(
            active=True,
            state="initializing",
            status="initializing",
            status_message="Starting Pi runtime.",
            error="",
            hardware=self._hardware_snapshot(enabled=False, action="initializing", error=""),
        )

        try:
            self._validate_startup()
            self._acquire_runtime_lock()
            self._setup_hardware()

            if self._hardware is not None:
                try:
                    self._hardware.indicate_boot()
                except Exception as exc:
                    self._disable_hardware(f"Boot output failed: {exc}")

            while not self._stop_event.is_set():
                cycle_started = time.monotonic()
                terminal_state = self._run_cycle()
                if self.config.once and terminal_state:
                    break
                elapsed = time.monotonic() - cycle_started
                remaining = max(self.config.loop_interval - elapsed, 0.0)
                if remaining > 0 and not self._stop_event.wait(remaining):
                    continue
                if remaining <= 0 and self._stop_event.is_set():
                    break
        except Exception as exc:
            self._enter_degraded(str(exc), action="startup_failed")
        finally:
            self._cleanup()

    def _validate_startup(self) -> None:
        if shutil.which("rpicam-still") is None:
            raise RuntimeConfigError("`rpicam-still` is not available on this backend.")
        if self.config.loop_interval <= 0:
            raise RuntimeConfigError("loop_interval must be > 0.")
        if self.config.stable_hold_seconds <= 0:
            raise RuntimeConfigError("stable_hold_seconds must be > 0.")
        if not 0 < self.config.presence.scene_error_border_fraction < 0.5:
            raise RuntimeConfigError("scene_error_border_fraction must be between 0 and 0.5.")

        classifier_python = resolve_repo_path(self.config.classifier_python)
        if not classifier_python.exists():
            raise RuntimeConfigError(f"Classifier Python interpreter does not exist: {classifier_python}")

        if not self.config.skip_presence_check:
            reference_path = resolve_repo_path(self.config.empty_reference)
            if not reference_path.exists():
                raise RuntimeConfigError(
                    "Blank calibration image is missing. Capture runtime/calibration/empty_plate.jpg first."
                )
            try:
                Image.open(reference_path).verify()
            except Exception as exc:
                raise RuntimeConfigError(f"Blank calibration image is unreadable: {exc}") from exc

        checkpoint_path = resolve_checkpoint_path(self.config.checkpoint_path)
        if not checkpoint_path.exists():
            raise RuntimeConfigError(f"Checkpoint does not exist: {checkpoint_path}")

        if self.config.startup_probe_classifier:
            probe_image: Path | None = None
            if not self.config.skip_presence_check:
                probe_image = resolve_repo_path(self.config.empty_reference)
            if probe_image is not None:
                self._probe_classifier(probe_image, checkpoint_path, classifier_python)

    def _probe_classifier(self, image_path: Path, checkpoint_path: Path, classifier_python: Path) -> None:
        command = [
            str(classifier_python),
            str(REPO_ROOT / "inference" / "pi" / "classify_image.py"),
            "--image",
            str(image_path),
            "--checkpoint",
            str(checkpoint_path),
            "--device",
            self.config.classifier_device,
            "--top-k",
            "1",
            "--json",
            "--no-record",
        ]
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeConfigError(
                completed.stderr.strip() or completed.stdout.strip() or "Classifier startup probe failed."
            )

    def _acquire_runtime_lock(self) -> None:
        lock_path = resolve_repo_path(self.config.lock_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeLockError(
                "Another TrashformerPro runtime already owns the Pi camera. Stop it before starting a new one."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os_getpid(), "started_at_utc": _utc_now_iso()}) + "\n")
        handle.flush()
        self._lock_handle = handle

    def _setup_hardware(self) -> None:
        if not self.config.hardware.enabled:
            self._hardware = None
            self._hardware_error = ""
            return
        if not gpio_outputs_supported():
            self._disable_hardware("GPIO outputs are not available on this backend.")
            return
        try:
            self._hardware = HardwareController(
                self.config.hardware.buzzer_mode,
                buzzer_pin=self.config.hardware.buzzer_pin,
                standby_reminder_seconds=self.config.hardware.standby_reminder_seconds,
            )
            self._hardware_error = ""
        except Exception as exc:
            self._disable_hardware(str(exc))

    def _disable_hardware(self, error_message: str) -> None:
        if self._hardware is not None:
            try:
                self._hardware.close()
            except Exception:
                pass
        self._hardware = None
        self._hardware_error = error_message

    def _run_cycle(self) -> bool:
        try:
            cycle = self._capture_cycle()
        except Exception as exc:
            self._capture_failures += 1
            self._reset_tracking()
            self._enter_degraded(f"Camera capture failed: {exc}", action="capture_failed")
            self._sleep_backoff()
            return True

        self._capture_failures = 0
        try:
            return self._process_cycle(cycle)
        except Exception as exc:
            self._reset_tracking()
            self._enter_degraded(str(exc), action="runtime_failed", image_path=cycle["image_path"])
            self._sleep_backoff()
            return True

    def _capture_cycle(self) -> dict[str, Any]:
        latest_capture_path = resolve_repo_path(self.config.latest_capture_path)
        latest_capture_path.parent.mkdir(parents=True, exist_ok=True)
        command = ["rpicam-still", "--nopreview", "-o", str(latest_capture_path)]
        camera_args = list(self.config.camera_args)
        if "--timeout" not in camera_args:
            camera_args.extend(["--timeout", str(DEFAULT_CAMERA_TIMEOUT_MS)])
        if camera_args:
            command.extend(camera_args)

        started_at = time.time()
        subprocess.run(command, check=True)
        image_data = latest_capture_path.read_bytes()
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        return {
            "image_path": latest_capture_path,
            "image_data": image_data,
            "image": image,
            "capture_time_ms": round((time.time() - started_at) * 1000, 2),
        }

    def _process_cycle(self, cycle: dict[str, Any]) -> bool:
        image_path = cycle["image_path"]
        image = cycle["image"]
        image_data = cycle["image_data"]
        capture_time_ms = cycle["capture_time_ms"]

        presence = None
        if not self.config.skip_presence_check:
            presence = analyze_frame_against_reference(
                image,
                reference_path=resolve_repo_path(self.config.empty_reference),
                presence=self.config.presence,
            )

        if presence is not None and presence.reference_scene_error:
            self._reset_tracking()
            self._apply_outputs("scene_error", None, None)
            scene_error_message = (
                "Object is too close to the camera or the plate framing changed too much."
                if presence.object_too_close
                else "Plate moved, disappeared, or framing changed too much."
            )
            self._record_state(
                state="scene_error",
                status_message=scene_error_message,
                error="",
                image_path=image_path,
                image_data=image_data,
                capture_time_ms=capture_time_ms,
                presence=presence,
                prediction=None,
                decision=None,
                confidence_passed=False,
                classification_triggered=False,
                classification_event_id=None,
                saved_capture_path=None,
                tracking={
                    "stable_for_seconds": 0.0,
                    "required_hold_seconds": self.config.stable_hold_seconds,
                    "object_id": None,
                },
            )
            self._log_event(
                image_path=image_path,
                outcome="scene_error",
                reason="reference_scene_changed",
                presence=presence,
            )
            return True

        if presence is not None and not presence.has_core_foreground:
            self._reset_tracking()
            self._apply_outputs("standby", None, None)
            self._record_state(
                state="standby",
                status_message="No object present on the plate.",
                error="",
                image_path=image_path,
                image_data=image_data,
                capture_time_ms=capture_time_ms,
                presence=presence,
                prediction=None,
                decision=None,
                confidence_passed=False,
                classification_triggered=False,
                classification_event_id=None,
                saved_capture_path=None,
                tracking={
                    "stable_for_seconds": 0.0,
                    "required_hold_seconds": self.config.stable_hold_seconds,
                    "object_id": None,
                },
            )
            return True

        now = time.monotonic()
        object_id = self._track_object(now, presence)
        stable_for_seconds = round(max(now - (self._object_started_at or now), 0.0), 2)
        tracking = {
            "stable_for_seconds": stable_for_seconds,
            "required_hold_seconds": self.config.stable_hold_seconds,
            "object_id": object_id,
        }

        if stable_for_seconds < self.config.stable_hold_seconds:
            self._apply_outputs("tracking", None, object_id)
            self._record_state(
                state="tracking",
                status_message="Object detected. Hold it steady for classification.",
                error="",
                image_path=image_path,
                image_data=image_data,
                capture_time_ms=capture_time_ms,
                presence=presence,
                prediction=None,
                decision=None,
                confidence_passed=False,
                classification_triggered=False,
                classification_event_id=None,
                saved_capture_path=None,
                tracking=tracking,
            )
            return False

        fresh_prediction = False
        if self._last_prediction is None or self._last_prediction.object_id != object_id:
            self._record_state(
                state="classifying",
                status_message="Object stable. Running classifier.",
                error="",
                image_path=image_path,
                image_data=image_data,
                capture_time_ms=capture_time_ms,
                presence=presence,
                prediction=None,
                decision=None,
                confidence_passed=False,
                classification_triggered=False,
                classification_event_id=None,
                saved_capture_path=None,
                tracking=tracking,
            )
            prediction_event = self._classify_current_object(image_path, image, object_id, presence)
            self._last_prediction = prediction_event
            fresh_prediction = True
            if self.prediction_callback is not None:
                self.prediction_callback(prediction_event.result)

        prediction_event = self._last_prediction
        assert prediction_event is not None
        top_prediction = prediction_event.result["predictions"][0]
        confidence = float(top_prediction["confidence"])
        is_low_confidence = confidence < self.config.min_confidence
        runtime_prediction = {
            "category": top_prediction["class_name"],
            "confidence": confidence,
            "model_source": prediction_event.result["checkpoint"],
            "checkpoint_sha256": prediction_event.result.get("checkpoint_sha256", ""),
            "model_name": prediction_event.result.get("model_name", ""),
            "inference_time_ms": prediction_event.result.get("inference_time_ms", 0.0),
        }
        terminal_tracking = {
            "stable_for_seconds": 0.0,
            "required_hold_seconds": self.config.stable_hold_seconds,
            "object_id": None,
        }

        next_state = "standby" if is_low_confidence else "classified"
        next_message = (
            "Prediction confidence below threshold. Returning to standby."
            if is_low_confidence
            else "Object held steady long enough. Classification locked."
        )
        self._apply_outputs("standby" if is_low_confidence else next_state, runtime_prediction, object_id)
        self._record_state(
            state=next_state,
            status_message=next_message,
            error="",
            image_path=image_path,
            image_data=image_data,
            capture_time_ms=capture_time_ms,
            presence=presence,
            prediction=runtime_prediction,
            decision="low_confidence" if is_low_confidence else "classified",
            confidence_passed=not is_low_confidence,
            classification_triggered=fresh_prediction and not is_low_confidence,
            classification_event_id=prediction_event.event_id if fresh_prediction and not is_low_confidence else None,
            saved_capture_path=prediction_event.archived_image_path,
            tracking=terminal_tracking,
        )
        if fresh_prediction:
            self._log_event(
                image_path=resolve_repo_path(Path(prediction_event.archived_image_path)),
                outcome="low_confidence" if is_low_confidence else next_state,
                reason="low_confidence" if is_low_confidence else "classified",
                presence=presence,
                prediction=prediction_event.result,
            )
        return True

    def _track_object(self, now: float, presence: PresenceAnalysis | None) -> str:
        bbox_pixels = presence.bbox_pixels if presence is not None else None
        same_object = _bbox_iou(self._last_bbox, bbox_pixels) >= CLASSIFICATION_IOU_THRESHOLD
        if same_object and self._object_started_at is not None:
            object_started_at = self._object_started_at
            object_id = self._last_object_id or f"obj-{int(object_started_at * 1000)}"
        else:
            object_started_at = now
            object_id = f"obj-{int(object_started_at * 1000)}"
            self._last_prediction = None

        self._object_started_at = object_started_at
        self._last_bbox = bbox_pixels
        self._last_object_id = object_id
        return object_id

    def _classify_current_object(
        self,
        latest_image_path: Path,
        image: Image.Image,
        object_id: str,
        presence: PresenceAnalysis | None,
    ) -> PredictionEvent:
        capture_stem = f"{self.config.capture_prefix}_locked_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        archived_full_path = CAPTURES_DIR / f"{capture_stem}_full.jpg"
        archived_path = CAPTURES_DIR / f"{capture_stem}.jpg"
        archived_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_image_path, archived_full_path)
        crop_image = _crop_image_for_presence(image, presence)
        crop_image.save(archived_path, format="JPEG", quality=95)
        checkpoint_path = resolve_checkpoint_path(self.config.checkpoint_path)
        classifier_python = resolve_repo_path(self.config.classifier_python)

        command = [
            str(classifier_python),
            str(REPO_ROOT / "inference" / "pi" / "classify_image.py"),
            "--image",
            str(archived_path),
            "--checkpoint",
            str(checkpoint_path),
            "--device",
            self.config.classifier_device,
            "--top-k",
            str(self.config.top_k),
            "--json",
        ]
        started_at = time.time()
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Classifier subprocess failed.")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Classifier returned invalid JSON.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            ) from exc

        payload["inference_time_ms"] = round((time.time() - started_at) * 1000, 2)
        event_id = hashlib.md5(f"{object_id}:{payload['timestamp_utc']}".encode("utf-8")).hexdigest()[:12]
        return PredictionEvent(
            event_id=event_id,
            object_id=object_id,
            archived_image_path=repo_relative(archived_path),
            result=payload,
        )

    def _record_state(
        self,
        *,
        state: str,
        status_message: str,
        error: str,
        image_path: Path | None,
        image_data: bytes | None,
        capture_time_ms: float,
        presence: PresenceAnalysis | None,
        prediction: dict[str, Any] | None,
        decision: str | None,
        confidence_passed: bool,
        classification_triggered: bool,
        classification_event_id: str | None,
        saved_capture_path: str | None,
        tracking: dict[str, Any],
    ) -> None:
        self._last_error = error
        self._set_snapshot(
            active=True,
            state=state,
            status=state,
            status_message=status_message,
            error=error,
            image_b64="",
            image_path=repo_relative(image_path) if image_path is not None else None,
            prediction=prediction,
            presence=presence.to_snapshot() if presence is not None else None,
            tracking=tracking,
            decision=decision,
            confidence_passed=confidence_passed,
            classification_triggered=classification_triggered,
            classification_event_id=classification_event_id,
            saved_capture_path=saved_capture_path,
            hardware=self._hardware_snapshot(
                enabled=self._hardware is not None,
                action=self._last_output_state,
                error=self._hardware_error,
            ),
            capture_time_ms=capture_time_ms,
        )
        if state != self._last_console_state:
            print(f"[runtime] {state}: {status_message}")
            if presence is not None:
                print(
                    "[runtime][presence]"
                    f" mean={presence.mean_diff:.2f}"
                    f" core_mean={presence.core_mean_diff:.2f}"
                    f" changed={presence.changed_ratio:.4f}"
                    f" core_changed={presence.core_changed_ratio:.4f}"
                    f" border_changed={presence.border_changed_ratio:.4f}"
                    f" bbox_area={presence.bbox_area_ratio:.4f}"
                    f" bbox_fill={presence.bbox_fill_ratio:.4f}"
                )
            self._last_console_state = state
        if error:
            print(f"[runtime][error] {error}")
        if classification_event_id and classification_event_id != self._last_console_event_id and prediction is not None:
            print(
                "[runtime][classification]"
                f" {prediction['category']} ({float(prediction['confidence']):.4f})"
            )
            self._last_console_event_id = classification_event_id

    def _apply_outputs(
        self,
        state: str,
        prediction: dict[str, Any] | None,
        object_id: str | None,
    ) -> None:
        if self._hardware is None:
            self._last_output_state = "disabled" if self.config.hardware.enabled else "idle"
            self._last_output_object_id = None
            return

        try:
            if state == "scene_error":
                if self._last_output_state != "scene_error":
                    self._hardware.play_sound("alert")
                    self._hardware.flash_all_leds(
                        self.config.hardware.alert_cycles,
                        self.config.hardware.alert_cycle_seconds,
                    )
                self._last_output_state = "scene_error"
                self._last_output_object_id = None
                return

            if state == "degraded":
                if self._last_output_state != "degraded":
                    self._hardware.play_sound("alert")
                self._last_output_state = "degraded"
                self._last_output_object_id = None
                return

            if state == "classified" and prediction and object_id:
                if self._last_output_state != "classified" or self._last_output_object_id != object_id:
                    self._hardware.indicate_category(
                        prediction["category"],
                        self.config.hardware.category_hold_seconds,
                    )
                self._last_output_state = "classified"
                self._last_output_object_id = object_id
                return

            if state in {"tracking", "classifying"}:
                self._hardware.indicate_tracking()
                self._last_output_state = state
                self._last_output_object_id = object_id
                return

            if state in {"standby", "low_confidence"}:
                self._hardware.indicate_standby(self.config.hardware.standby_reminder_seconds)
                self._last_output_state = state
                self._last_output_object_id = None
                return

            self._hardware.clear()
            self._last_output_state = "idle"
            self._last_output_object_id = None
        except Exception as exc:
            self._disable_hardware(f"Hardware output failed: {exc}")
            self._last_output_state = "error"

    def _enter_degraded(self, error_message: str, *, action: str, image_path: Path | None = None) -> None:
        self._apply_outputs("degraded", None, None)
        self._record_state(
            state="degraded",
            status_message="Runtime is degraded and will retry automatically.",
            error=error_message,
            image_path=image_path,
            image_data=image_path.read_bytes() if image_path is not None and image_path.exists() else None,
            capture_time_ms=0.0,
            presence=None,
            prediction=None,
            decision=None,
            confidence_passed=False,
            classification_triggered=False,
            classification_event_id=None,
            saved_capture_path=None,
            tracking={
                "stable_for_seconds": 0.0,
                "required_hold_seconds": self.config.stable_hold_seconds,
                "object_id": None,
            },
        )
        self._log_event(image_path=image_path, outcome="degraded", reason=action, error=error_message)

    def _sleep_backoff(self) -> None:
        seconds = min(max(float(self._capture_failures), 1.0), 5.0)
        if self._stop_event is not None:
            self._stop_event.wait(seconds)
        else:
            time.sleep(seconds)

    def _reset_tracking(self) -> None:
        self._object_started_at = None
        self._last_bbox = None
        self._last_object_id = None
        self._last_prediction = None

    def _log_event(
        self,
        *,
        image_path: Path | None,
        outcome: str,
        reason: str,
        presence: PresenceAnalysis | None = None,
        prediction: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        log_path = resolve_repo_path(self.config.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "timestamp_utc": _utc_now_iso(),
            "outcome": outcome,
            "reason": reason,
            "error": error,
        }
        if image_path is not None:
            payload["image_path"] = repo_relative(image_path)
        if presence is not None:
            payload["presence"] = presence.to_snapshot()
        if prediction is not None:
            payload["prediction"] = prediction
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _cleanup(self) -> None:
        if self._hardware is not None:
            try:
                self._hardware.play_sound("shutdown")
            except Exception:
                pass
            try:
                self._hardware.close()
            except Exception:
                pass
            self._hardware = None

        if self._lock_handle is not None:
            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self._lock_handle.close()
            self._lock_handle = None

        self._set_snapshot(
            active=False,
            state="standby",
            status="standby",
            status_message="Runtime stopped.",
            hardware=self._hardware_snapshot(enabled=False, action="disabled", error=self._hardware_error),
        )


def os_getpid() -> int:
    try:
        import os

        return os.getpid()
    except Exception:
        return -1
