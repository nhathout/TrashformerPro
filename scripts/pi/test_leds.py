#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pi.hardware_config import GPIO_TO_PHYSICAL_PIN, LED_GPIO_PINS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cycle through the four TrashformerPro status LEDs on a Raspberry Pi.")
    parser.add_argument("--hold-seconds", type=float, default=0.6, help="How long each LED stays on.")
    parser.add_argument("--gap-seconds", type=float, default=0.2, help="Pause between LED changes.")
    parser.add_argument("--cycles", type=int, default=2, help="How many times to run the LED sequence.")
    parser.add_argument(
        "--skip-all-on",
        action="store_true",
        help="Skip the final step where all LEDs turn on together.",
    )
    return parser.parse_args()


def import_gpiozero():
    try:
        from gpiozero import LED  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "gpiozero is not installed for this Python interpreter. "
            "On the Pi, run `bash scripts/pi/setup_pi.sh` first."
        ) from exc
    return LED


def main() -> None:
    args = parse_args()
    LED = import_gpiozero()

    leds = {name: LED(pin) for name, pin in LED_GPIO_PINS.items()}
    try:
        print("Testing LEDs with BCM pin numbering:")
        for name, pin in LED_GPIO_PINS.items():
            print(f"  {name}: GPIO{pin} (physical pin {GPIO_TO_PHYSICAL_PIN[pin]})")

        for cycle_index in range(args.cycles):
            print(f"Cycle {cycle_index + 1}/{args.cycles}")
            for name, led in leds.items():
                print(f"  Turning on {name}")
                led.on()
                time.sleep(args.hold_seconds)
                led.off()
                time.sleep(args.gap_seconds)

        if not args.skip_all_on:
            print("Turning all LEDs on together")
            for led in leds.values():
                led.on()
            time.sleep(args.hold_seconds)
            for led in leds.values():
                led.off()

        print("LED test complete.")
    finally:
        for led in leds.values():
            led.close()


if __name__ == "__main__":
    main()
