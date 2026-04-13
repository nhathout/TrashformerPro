#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_utils import capture_image, ensure_runtime_dirs, repo_relative, resolve_repo_path
from scripts.pi.hardware_config import BUZZER_GPIO_PIN, GPIO_TO_PHYSICAL_PIN, LED_GPIO_PINS

DEFAULT_CLASSIFIER_PYTHON = Path(".venv/bin/python")
DEFAULT_REFERENCE_PATH = Path("runtime/calibration/empty_plate.jpg")
DEFAULT_LOG_PATH = Path("runtime/logs/full_system_events.jsonl")

PASSIVE_PATTERNS: dict[str, list[tuple[float | None, float]]] = {
    "boot": [(523.25, 0.08), (659.25, 0.08), (783.99, 0.10), (1046.50, 0.14)],
    "shutdown": [(1046.50, 0.08), (783.99, 0.08), (659.25, 0.10), (523.25, 0.16)],
    "alert": [(392.00, 0.10), (None, 0.05), (329.63, 0.10), (None, 0.05), (261.63, 0.18)],
    "plastic": [(880.00, 0.07), (1046.50, 0.07), (1318.51, 0.12)],
    "paper_cardboard": [(587.33, 0.09), (698.46, 0.09), (880.00, 0.11)],
    "metal_glass": [(1318.51, 0.08), (987.77, 0.08), (1567.98, 0.14)],
    "trash_other": [(659.25, 0.08), (523.25, 0.08), (392.00, 0.12), (261.63, 0.14)],
}

ACTIVE_PATTERNS: dict[str, list[tuple[bool, float]]] = {
    "boot": [(True, 0.06), (False, 0.04), (True, 0.06), (False, 0.04), (True, 0.12)],
    "shutdown": [(True, 0.10), (False, 0.05), (True, 0.08), (False, 0.05), (True, 0.06)],
    "alert": [(True, 0.10), (False, 0.05), (True, 0.10), (False, 0.05), (True, 0.18)],
    "plastic": [(True, 0.04), (False, 0.03), (True, 0.04), (False, 0.03), (True, 0.10)],
    "paper_cardboard": [(True, 0.08), (False, 0.04), (True, 0.08), (False, 0.04), (True, 0.08)],
    "metal_glass": [(True, 0.03), (False, 0.03), (True, 0.03), (False, 0.03), (True, 0.12)],
    "trash_other": [(True, 0.14), (False, 0.05), (True, 0.08), (False, 0.05), (True, 0.05)],
}


def import_cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "OpenCV is not installed for this Python interpreter. Run `bash scripts/pi/setup_pi.sh` first."
        ) from exc
    return cv2


def import_gpiozero():
    try:
        from gpiozero import Buzzer, LED, PWMOutputDevice  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "gpiozero is not installed for this Python interpreter. Run `bash scripts/pi/setup_pi.sh` first."
        ) from exc
    return LED, Buzzer, PWMOutputDevice


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full TrashformerPro Pi loop: capture, classify, LEDs, and buzzer."
    )
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to the trained model checkpoint.")
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
    parser.add_argument("--loop-interval", type=float, default=1.0)
    parser.add_argument("--decision-hold-seconds", type=float, default=2.5)
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
    parser.add_argument("--once", action="store_true", help="Run one capture/classify/output cycle, then exit.")
    return parser.parse_args()


@dataclass
class PresenceResult:
    object_present: bool
    mean_diff: float
    changed_ratio: float
    pixel_threshold: int
    ratio_threshold: float
    mean_threshold: float


class HardwareController:
    def __init__(self, buzzer_mode: str, buzzer_pin: int) -> None:
        LED, Buzzer, PWMOutputDevice = import_gpiozero()
        self.leds = {name: LED(pin) for name, pin in LED_GPIO_PINS.items()}
        self.buzzer_mode = buzzer_mode
        self.buzzer_pin = buzzer_pin
        self.buzzer = None

        if buzzer_mode == "active":
            self.buzzer = Buzzer(buzzer_pin)
        elif buzzer_mode == "passive":
            self.buzzer = PWMOutputDevice(buzzer_pin, frequency=440.0)
            self.buzzer.off()

    def close(self) -> None:
        self.all_leds_off()
        if self.buzzer is not None:
            self.buzzer.off()
            self.buzzer.close()
        for led in self.leds.values():
            led.close()

    def all_leds_off(self) -> None:
        for led in self.leds.values():
            led.off()

    def flash_all_leds(self, cycles: int, cycle_seconds: float) -> None:
        on_seconds = max(cycle_seconds / 2.0, 0.0)
        off_seconds = max(cycle_seconds - on_seconds, 0.0)
        for _ in range(cycles):
            for led in self.leds.values():
                led.on()
            time.sleep(on_seconds)
            self.all_leds_off()
            time.sleep(off_seconds)

    def indicate_category(self, category: str, hold_seconds: float) -> None:
        self.all_leds_off()
        led = self.leds[category]
        led.on()
        sound_duration = self.play_sound(category)
        remaining = max(hold_seconds - sound_duration, 0.0)
        if remaining > 0:
            time.sleep(remaining)
        led.off()

    def play_sound(self, sound_name: str) -> float:
        if self.buzzer_mode == "none" or self.buzzer is None:
            return 0.0

        if self.buzzer_mode == "passive":
            return self._play_passive(sound_name)
        return self._play_active(sound_name)

    def _play_passive(self, sound_name: str) -> float:
        pattern = PASSIVE_PATTERNS[sound_name]
        total = 0.0
        for frequency, duration in pattern:
            total += duration
            if frequency is None:
                self.buzzer.off()
                time.sleep(duration)
                continue
            self.buzzer.frequency = frequency
            self.buzzer.value = 0.5
            time.sleep(duration)
            self.buzzer.off()
            time.sleep(0.02)
            total += 0.02
        return total

    def _play_active(self, sound_name: str) -> float:
        pattern = ACTIVE_PATTERNS[sound_name]
        total = 0.0
        for enabled, duration in pattern:
            total += duration
            if enabled:
                self.buzzer.on()
            else:
                self.buzzer.off()
            time.sleep(duration)
        self.buzzer.off()
        return total


def load_grayscale_image(path: Path, size: int):
    cv2 = import_cv2()
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"Could not read image at {path}")
    image = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(image, (5, 5), 0)


def evaluate_presence(
    reference_path: Path,
    image_path: Path,
    *,
    resize: int,
    pixel_threshold: int,
    ratio_threshold: float,
    mean_threshold: float,
) -> PresenceResult:
    cv2 = import_cv2()
    reference = load_grayscale_image(reference_path, resize)
    current = load_grayscale_image(image_path, resize)

    difference = cv2.absdiff(reference, current)
    mean_diff = float(difference.mean())
    _, changed_mask = cv2.threshold(difference, pixel_threshold, 255, cv2.THRESH_BINARY)
    changed_ratio = float(changed_mask.mean() / 255.0)
    object_present = changed_ratio >= ratio_threshold or mean_diff >= mean_threshold

    return PresenceResult(
        object_present=object_present,
        mean_diff=mean_diff,
        changed_ratio=changed_ratio,
        pixel_threshold=pixel_threshold,
        ratio_threshold=ratio_threshold,
        mean_threshold=mean_threshold,
    )


def run_classifier(
    classifier_python: Path,
    image_path: Path,
    checkpoint_path: Path,
    *,
    device: str,
    top_k: int,
) -> dict[str, Any]:
    command = [
        str(classifier_python),
        str(REPO_ROOT / "inference" / "pi" / "classify_image.py"),
        "--image",
        str(image_path),
        "--checkpoint",
        str(checkpoint_path),
        "--device",
        device,
        "--top-k",
        str(top_k),
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Classifier subprocess failed.")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Classifier returned invalid JSON.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        ) from exc


def log_event(path: Path, payload: dict[str, Any]) -> None:
    log_path = resolve_repo_path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def build_event(
    *,
    image_path: Path | None,
    outcome: str,
    reason: str,
    presence: PresenceResult | None = None,
    prediction: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "reason": reason,
        "error": error,
    }
    if image_path is not None:
        event["image_path"] = repo_relative(image_path)
    if presence is not None:
        event["presence"] = asdict(presence)
    if prediction is not None:
        event["prediction"] = prediction
    return event


def resolve_existing_path(path: Path, description: str) -> Path:
    resolved = resolve_repo_path(path)
    if not resolved.exists():
        raise SystemExit(f"{description} does not exist: {resolved}")
    return resolved


def sleep_until_next_cycle(started_at: float, loop_interval: float) -> None:
    elapsed = time.time() - started_at
    remaining = max(loop_interval - elapsed, 0.0)
    if remaining > 0:
        time.sleep(remaining)


def main() -> None:
    args = parse_args()
    ensure_runtime_dirs()

    checkpoint_path = resolve_existing_path(args.checkpoint, "Checkpoint")
    classifier_python = resolve_existing_path(args.classifier_python, "Classifier Python interpreter")
    empty_reference_path = resolve_repo_path(args.empty_reference)

    if not args.skip_presence_check and not empty_reference_path.exists():
        raise SystemExit(
            "Empty reference image not found. Capture one with "
            "`/usr/bin/python3 scripts/pi/capture_empty_reference.py` or rerun with --skip-presence-check."
        )

    print("Starting full TrashformerPro Pi loop")
    print(f"  checkpoint: {repo_relative(checkpoint_path)}")
    print(f"  classifier python: {repo_relative(classifier_python)}")
    if args.skip_presence_check:
        print("  presence check: disabled")
    else:
        print(f"  empty reference: {repo_relative(empty_reference_path)}")
    print(f"  buzzer mode: {args.buzzer_mode} on GPIO{args.buzzer_pin} (physical pin {GPIO_TO_PHYSICAL_PIN.get(args.buzzer_pin, 'unknown')})")

    controller: HardwareController | None = None

    try:
        controller = HardwareController(args.buzzer_mode, args.buzzer_pin)
        controller.play_sound("boot")

        while True:
            cycle_started = time.time()
            image_path: Path | None = None

            try:
                image_path = capture_image(
                    prefix=args.capture_prefix,
                    camera_args=args.camera_arg,
                )
                print(f"Captured: {repo_relative(image_path)}")
            except Exception as exc:
                error_message = f"Capture failed: {exc}"
                print(error_message)
                controller.play_sound("alert")
                controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
                log_event(
                    args.log_path,
                    build_event(
                        image_path=None,
                        outcome="alert",
                        reason="capture_failed",
                        error=str(exc),
                    ),
                )
                if args.once:
                    raise SystemExit(error_message) from exc
                sleep_until_next_cycle(cycle_started, args.loop_interval)
                continue

            presence_result: PresenceResult | None = None
            if not args.skip_presence_check:
                try:
                    presence_result = evaluate_presence(
                        empty_reference_path,
                        image_path,
                        resize=args.presence_resize,
                        pixel_threshold=args.presence_pixel_threshold,
                        ratio_threshold=args.presence_ratio_threshold,
                        mean_threshold=args.presence_mean_threshold,
                    )
                except Exception as exc:
                    error_message = f"Presence check failed: {exc}"
                    print(error_message)
                    controller.play_sound("alert")
                    controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
                    log_event(
                        args.log_path,
                        build_event(
                            image_path=image_path,
                            outcome="alert",
                            reason="presence_check_failed",
                            error=str(exc),
                        ),
                    )
                    if args.once:
                        raise SystemExit(error_message) from exc
                    sleep_until_next_cycle(cycle_started, args.loop_interval)
                    continue

                print(
                    "Presence metrics:"
                    f" mean_diff={presence_result.mean_diff:.2f}"
                    f" changed_ratio={presence_result.changed_ratio:.4f}"
                    f" object_present={presence_result.object_present}"
                )
                if not presence_result.object_present:
                    print("No object detected in frame. Triggering alert state.")
                    controller.play_sound("alert")
                    controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
                    log_event(
                        args.log_path,
                        build_event(
                            image_path=image_path,
                            outcome="alert",
                            reason="no_object_detected",
                            presence=presence_result,
                        ),
                    )
                    if args.once:
                        break
                    sleep_until_next_cycle(cycle_started, args.loop_interval)
                    continue

            try:
                prediction = run_classifier(
                    classifier_python,
                    image_path,
                    checkpoint_path,
                    device=args.classifier_device,
                    top_k=args.top_k,
                )
            except Exception as exc:
                error_message = f"Classification failed: {exc}"
                print(error_message)
                controller.play_sound("alert")
                controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
                log_event(
                    args.log_path,
                    build_event(
                        image_path=image_path,
                        outcome="alert",
                        reason="classification_failed",
                        presence=presence_result,
                        error=str(exc),
                    ),
                )
                if args.once:
                    raise SystemExit(error_message) from exc
                sleep_until_next_cycle(cycle_started, args.loop_interval)
                continue

            top_prediction = prediction["predictions"][0]
            predicted_class = top_prediction["class_name"]
            confidence = float(top_prediction["confidence"])
            print(f"Predicted {predicted_class} with confidence {confidence:.4f}")

            if confidence < args.min_confidence:
                print(
                    f"Confidence below threshold ({confidence:.4f} < {args.min_confidence:.4f}). Triggering alert state."
                )
                controller.play_sound("alert")
                controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
                log_event(
                    args.log_path,
                    build_event(
                        image_path=image_path,
                        outcome="alert",
                        reason="low_confidence",
                        presence=presence_result,
                        prediction=prediction,
                    ),
                )
            else:
                controller.indicate_category(predicted_class, args.decision_hold_seconds)
                log_event(
                    args.log_path,
                    build_event(
                        image_path=image_path,
                        outcome="success",
                        reason="classified",
                        presence=presence_result,
                        prediction=prediction,
                    ),
                )

            if args.once:
                break

            sleep_until_next_cycle(cycle_started, args.loop_interval)
    except KeyboardInterrupt:
        print("Stopping full TrashformerPro Pi loop.")
    finally:
        if controller is not None:
            controller.play_sound("shutdown")
            controller.close()


if __name__ == "__main__":
    main()
