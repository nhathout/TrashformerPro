#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_utils import describe_checkpoint_file, ensure_runtime_dirs, repo_relative, resolve_checkpoint_path, resolve_repo_path
from scripts.pi.hardware_config import BUZZER_GPIO_PIN, GPIO_TO_PHYSICAL_PIN

if TYPE_CHECKING:
    from inference.pi.runtime_engine import PiRuntimeEngine, RuntimeConfig

DEFAULT_CLASSIFIER_PYTHON = Path(".venv/bin/python")
DEFAULT_REFERENCE_PATH = Path("runtime/calibration/empty_plate.jpg")
DEFAULT_ROBOT_CAPTURE_PATH = Path("runtime/captures/fullrun_latest.jpg")
DEFAULT_STABLE_HOLD_SECONDS = 2.0
DEFAULT_LOOP_INTERVAL = 1.0
DEFAULT_CATEGORY_HOLD_SECONDS = 2.0
DEFAULT_STANDBY_REMINDER_SECONDS = 20.0
DEFAULT_LOG_PATH = Path("runtime/logs/full_system_events.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full TrashformerPro Pi loop: capture, classify, LEDs, and buzzer output."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Path to the trained model checkpoint. Defaults to models/best.pt, then runtime/models/best.pt.",
    )
    parser.add_argument(
        "--classifier-python",
        type=Path,
        default=DEFAULT_CLASSIFIER_PYTHON,
        help="Python interpreter that has torch/torchvision installed for inference.",
    )
    parser.add_argument("--classifier-device", type=str, default="cpu", help="Inference device passed to classify_image.py.")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--min-confidence", type=float, default=0.70)
    parser.add_argument("--capture-prefix", type=str, default="fullrun")
    parser.add_argument(
        "--camera-arg",
        action="append",
        default=[],
        help="Extra argument passed directly to rpicam-still. Repeat this flag for multiple arguments.",
    )
    parser.add_argument(
        "--empty-reference",
        type=Path,
        default=DEFAULT_REFERENCE_PATH,
        help="Reference image of the empty plate used to decide whether an object is present.",
    )
    parser.add_argument(
        "--skip-presence-check",
        action="store_true",
        help="Disable the empty-frame comparison and always attempt classification.",
    )
    parser.add_argument("--presence-resize", type=int, default=256)
    parser.add_argument("--presence-pixel-threshold", type=int, default=18)
    parser.add_argument("--presence-ratio-threshold", type=float, default=0.015)
    parser.add_argument("--presence-mean-threshold", type=float, default=8.0)
    parser.add_argument(
        "--scene-error-border-fraction",
        type=float,
        default=0.18,
        help="Outer border fraction used to detect if the plate or camera framing changed too much.",
    )
    parser.add_argument(
        "--scene-error-ratio-threshold",
        type=float,
        default=0.12,
        help="Alert when the border-region changed-ratio reaches this threshold.",
    )
    parser.add_argument(
        "--scene-error-mean-threshold",
        type=float,
        default=14.0,
        help="Alert when the border-region mean difference reaches this threshold.",
    )
    parser.add_argument("--loop-interval", type=float, default=DEFAULT_LOOP_INTERVAL)
    parser.add_argument(
        "--stable-hold-seconds",
        type=float,
        default=DEFAULT_STABLE_HOLD_SECONDS,
        help="How long the same object must remain stable before the classifier runs.",
    )
    parser.add_argument(
        "--standby-reminder-seconds",
        type=float,
        default=DEFAULT_STANDBY_REMINDER_SECONDS,
        help="How often standby may make a reminder beep. Set to 0 to make standby fully silent.",
    )
    parser.add_argument(
        "--category-hold-seconds",
        type=float,
        default=DEFAULT_CATEGORY_HOLD_SECONDS,
        help="How long a category LED stays on after a confident classification.",
    )
    parser.add_argument(
        "--decision-hold-seconds",
        type=float,
        default=None,
        help="Deprecated alias for --category-hold-seconds.",
    )
    parser.add_argument("--alert-cycles", type=int, default=3)
    parser.add_argument(
        "--alert-cycle-seconds",
        type=float,
        default=1.0,
        help="A full flash cycle duration. The LEDs stay on for half the cycle and off for half.",
    )
    parser.add_argument(
        "--buzzer-mode",
        choices=("active", "passive", "none"),
        default="active",
        help="Choose passive for a piezo buzzer, active for simple on/off beeps, or none to disable sounds.",
    )
    parser.add_argument("--buzzer-pin", type=int, default=BUZZER_GPIO_PIN)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--once", action="store_true", help="Run until the first terminal runtime decision, then exit.")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> "RuntimeConfig":
    from inference.pi.runtime_engine import HardwareConfig, PresenceConfig, RuntimeConfig

    category_hold_seconds = (
        args.decision_hold_seconds
        if args.decision_hold_seconds is not None
        else args.category_hold_seconds
    )
    return RuntimeConfig(
        checkpoint_path=args.checkpoint,
        classifier_python=args.classifier_python,
        classifier_device=args.classifier_device,
        top_k=args.top_k,
        min_confidence=args.min_confidence,
        capture_prefix=args.capture_prefix,
        latest_capture_path=DEFAULT_ROBOT_CAPTURE_PATH,
        camera_args=tuple(args.camera_arg),
        empty_reference=args.empty_reference,
        skip_presence_check=args.skip_presence_check,
        presence=PresenceConfig(
            resize=args.presence_resize,
            pixel_threshold=args.presence_pixel_threshold,
            ratio_threshold=args.presence_ratio_threshold,
            mean_threshold=args.presence_mean_threshold,
            scene_error_border_fraction=args.scene_error_border_fraction,
            scene_error_ratio_threshold=args.scene_error_ratio_threshold,
            scene_error_mean_threshold=args.scene_error_mean_threshold,
        ),
        loop_interval=args.loop_interval,
        stable_hold_seconds=args.stable_hold_seconds,
        hardware=HardwareConfig(
            enabled=True,
            buzzer_mode=args.buzzer_mode,
            buzzer_pin=args.buzzer_pin,
            standby_reminder_seconds=args.standby_reminder_seconds,
            category_hold_seconds=category_hold_seconds,
            alert_cycles=args.alert_cycles,
            alert_cycle_seconds=args.alert_cycle_seconds,
        ),
        log_path=args.log_path,
        once=args.once,
    )


def print_runtime_header(config: RuntimeConfig) -> None:
    checkpoint_info = describe_checkpoint_file(config.checkpoint_path)
    classifier_python = resolve_repo_path(config.classifier_python)
    print("Starting full TrashformerPro Pi loop")
    print(
        f"  checkpoint: {checkpoint_info['checkpoint']} "
        f"[{str(checkpoint_info['checkpoint_sha256'])[:12]}]"
    )
    print(f"  classifier python: {repo_relative(classifier_python)}")
    if config.skip_presence_check:
        print("  presence check: disabled")
    else:
        print(f"  empty reference: {repo_relative(resolve_repo_path(config.empty_reference))}")
    print(f"  stable hold: {config.stable_hold_seconds:.1f}s")
    print(
        f"  buzzer mode: {config.hardware.buzzer_mode} on GPIO{config.hardware.buzzer_pin} "
        f"(physical pin {GPIO_TO_PHYSICAL_PIN.get(config.hardware.buzzer_pin, 'unknown')})"
    )


def print_snapshot(snapshot: dict[str, object], last_state: dict[str, object]) -> dict[str, object]:
    state = snapshot.get("state")
    error = snapshot.get("error")
    tracking = snapshot.get("tracking") or {}
    presence = snapshot.get("presence") or {}
    prediction = snapshot.get("prediction") or {}
    classification_event_id = snapshot.get("classification_event_id")

    if state != last_state.get("state"):
        print(f"[state] {state}: {snapshot.get('status_message')}")

    if (
        state == "tracking"
        and tracking.get("object_id") != last_state.get("object_id")
        and tracking.get("object_id") is not None
    ):
        print(f"[tracking] object detected; waiting {tracking.get('required_hold_seconds', 0.0):.1f}s to classify.")

    if state in {"standby", "scene_error"} and presence:
        print(
            "[presence]"
            f" mean_diff={float(presence.get('mean_diff', 0.0)):.2f}"
            f" changed_ratio={float(presence.get('changed_ratio', 0.0)):.4f}"
            f" border_mean_diff={float(presence.get('border_mean_diff', 0.0)):.2f}"
            f" border_changed_ratio={float(presence.get('border_changed_ratio', 0.0)):.4f}"
        )

    if classification_event_id and classification_event_id != last_state.get("classification_event_id"):
        print(
            "[classification]"
            f" {prediction.get('category')} ({float(prediction.get('confidence', 0.0)):.4f})"
        )

    if error and error != last_state.get("error"):
        print(f"[error] {error}")

    return {
        "state": state,
        "object_id": tracking.get("object_id"),
        "classification_event_id": classification_event_id,
        "error": error,
    }


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()
    config = build_config(args)
    print_runtime_header(config)

    from inference.pi.runtime_engine import PiRuntimeEngine

    engine = PiRuntimeEngine(config)
    thread = threading.Thread(target=engine.run_forever, daemon=True)
    last_state: dict[str, object] = {}
    thread.start()

    try:
        while thread.is_alive():
            snapshot = engine.get_snapshot()
            if snapshot.get("active") or snapshot.get("error"):
                last_state = print_snapshot(snapshot, last_state)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Stopping full TrashformerPro Pi loop.")
        engine.stop()
        thread.join(timeout=5.0)
    else:
        thread.join(timeout=5.0)


if __name__ == "__main__":
    main()
