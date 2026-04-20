#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.hardware_outputs import DEFAULT_STANDBY_REMINDER_SECONDS, HardwareController
from scripts.pi.hardware_config import BUZZER_GPIO_PIN, LED_GPIO_PINS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drive the TrashformerPro Pi LEDs and buzzer once.")
    parser.add_argument(
        "--action",
        choices=("boot", "shutdown", "standby", "alert", "category", "clear"),
        required=True,
    )
    parser.add_argument("--category", choices=tuple(LED_GPIO_PINS.keys()))
    parser.add_argument("--buzzer-mode", choices=("active", "passive", "none"), default="passive")
    parser.add_argument("--buzzer-pin", type=int, default=BUZZER_GPIO_PIN)
    parser.add_argument("--standby-reminder-seconds", type=float, default=DEFAULT_STANDBY_REMINDER_SECONDS)
    parser.add_argument("--category-hold-seconds", type=float, default=2.0)
    parser.add_argument("--alert-cycles", type=int, default=3)
    parser.add_argument("--alert-cycle-seconds", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    controller = HardwareController(
        args.buzzer_mode,
        buzzer_pin=args.buzzer_pin,
        standby_reminder_seconds=args.standby_reminder_seconds,
    )
    try:
        if args.action == "boot":
            controller.play_sound("boot")
        elif args.action == "shutdown":
            controller.play_sound("shutdown")
        elif args.action == "standby":
            controller.indicate_standby(args.standby_reminder_seconds)
        elif args.action == "alert":
            controller.play_sound("alert")
            controller.flash_all_leds(args.alert_cycles, args.alert_cycle_seconds)
        elif args.action == "category":
            if not args.category:
                raise SystemExit("--category is required when --action category is used.")
            controller.indicate_category(args.category, args.category_hold_seconds)
        elif args.action == "clear":
            controller.clear()
    finally:
        controller.close()


if __name__ == "__main__":
    main()
