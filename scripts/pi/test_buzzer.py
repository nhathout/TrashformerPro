#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pi.hardware_config import BUZZER_GPIO_PIN, GPIO_TO_PHYSICAL_PIN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test a simple buzzer connected to the Raspberry Pi.")
    parser.add_argument(
        "--mode",
        choices=("active", "passive"),
        default="active",
        help="Use active for a simple on/off buzzer or passive for a piezo buzzer that can play tones.",
    )
    parser.add_argument("--pin", type=int, default=BUZZER_GPIO_PIN, help="BCM GPIO pin for the buzzer signal.")
    parser.add_argument("--count", type=int, default=3, help="How many beeps or tones to emit.")
    parser.add_argument("--on-seconds", type=float, default=0.2, help="How long each active-buzzer beep lasts.")
    parser.add_argument("--off-seconds", type=float, default=0.2, help="Gap between beeps or tones.")
    parser.add_argument(
        "--frequency",
        type=float,
        default=440.0,
        help="Starting frequency for passive mode.",
    )
    return parser.parse_args()


def import_gpiozero():
    try:
        from gpiozero import Buzzer, PWMOutputDevice  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "gpiozero is not installed for this Python interpreter. "
            "On the Pi, run `bash scripts/pi/setup_pi.sh` first."
        ) from exc
    return Buzzer, PWMOutputDevice


def run_active_test(Buzzer, pin: int, count: int, on_seconds: float, off_seconds: float) -> None:
    buzzer = Buzzer(pin)
    try:
        for index in range(count):
            print(f"Beep {index + 1}/{count}")
            buzzer.on()
            time.sleep(on_seconds)
            buzzer.off()
            time.sleep(off_seconds)
    finally:
        buzzer.close()


def run_passive_test(PWMOutputDevice, pin: int, count: int, frequency: float, off_seconds: float) -> None:
    buzzer = PWMOutputDevice(pin, frequency=frequency)
    tones = [frequency * ratio for ratio in (0.75, 1.0, 1.25, 1.5)]
    try:
        for index in range(count):
            target_frequency = tones[index % len(tones)]
            print(f"Tone {index + 1}/{count} at {target_frequency:.1f} Hz")
            buzzer.frequency = target_frequency
            buzzer.value = 0.28
            time.sleep(0.25)
            buzzer.off()
            time.sleep(off_seconds)
    finally:
        buzzer.close()


def main() -> None:
    args = parse_args()
    Buzzer, PWMOutputDevice = import_gpiozero()

    physical_pin = GPIO_TO_PHYSICAL_PIN.get(args.pin, "unknown")
    print(f"Testing buzzer on GPIO{args.pin} (physical pin {physical_pin}) in {args.mode} mode")

    if args.mode == "active":
        run_active_test(Buzzer, args.pin, args.count, args.on_seconds, args.off_seconds)
    else:
        run_passive_test(PWMOutputDevice, args.pin, args.count, args.frequency, args.off_seconds)

    print("Buzzer test complete.")


if __name__ == "__main__":
    main()
