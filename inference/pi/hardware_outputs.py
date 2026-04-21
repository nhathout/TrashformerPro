from __future__ import annotations

import site
import sys
import time
from pathlib import Path

from scripts.pi.hardware_config import BUZZER_GPIO_PIN, LED_GPIO_PINS

DEFAULT_STANDBY_REMINDER_SECONDS = 15.0
PASSIVE_BUZZER_LEVEL = 1.0


def milliseconds(value: float) -> float:
    return value / 1000.0


def tone_steps(
    frequency: float,
    note_duration_ms: float,
    silent_duration_ms: float = 0.0,
) -> list[tuple[float | None, float]]:
    pattern: list[tuple[float | None, float]] = [(frequency, milliseconds(note_duration_ms))]
    if silent_duration_ms > 0:
        pattern.append((None, milliseconds(silent_duration_ms)))
    return pattern


def bend_tone_steps(
    init_frequency: float,
    final_frequency: float,
    prop: float,
    note_duration_ms: float,
    silent_duration_ms: float,
) -> list[tuple[float | None, float]]:
    pattern: list[tuple[float | None, float]] = []
    frequency = init_frequency

    if init_frequency < final_frequency:
        while frequency < final_frequency:
            pattern.extend(tone_steps(frequency, note_duration_ms, silent_duration_ms))
            frequency *= prop
    else:
        while frequency > final_frequency:
            pattern.extend(tone_steps(frequency, note_duration_ms, silent_duration_ms))
            frequency /= prop

    return pattern


PASSIVE_PATTERNS: dict[str, list[tuple[float | None, float]]] = {
    "boot": [
        (261.63, 0.14),
        (None, 0.06),
        (392.00, 0.18),
    ],
    "shutdown": [
        (392.00, 0.14),
        (None, 0.06),
        (261.63, 0.18),
    ],
    "standby": [(246.94, 0.03)],
    "alert": [(220.00, 0.12), (None, 0.05), (220.00, 0.12), (None, 0.05), (196.00, 0.18)],
    "plastic": [(523.25, 0.16)],
    "paper_cardboard": [(349.23, 0.16)],
    "metal_glass": [(659.25, 0.18)],
    "trash_other": [(246.94, 0.18)],
}

ACTIVE_PATTERNS: dict[str, list[tuple[bool, float]]] = {
    "boot": [(True, 0.12), (False, 0.06), (True, 0.18)],
    "shutdown": [(True, 0.18), (False, 0.06), (True, 0.12)],
    "standby": [(True, 0.02)],
    "alert": [(True, 0.12), (False, 0.05), (True, 0.12), (False, 0.05), (True, 0.18)],
    "plastic": [(True, 0.12)],
    "paper_cardboard": [(True, 0.12)],
    "metal_glass": [(True, 0.15)],
    "trash_other": [(True, 0.18)],
}


def gpio_outputs_supported() -> bool:
    try:
        import_gpiozero()
    except RuntimeError:
        return False
    return True


def import_gpiozero():
    try:
        from gpiozero import Buzzer, LED, PWMOutputDevice  # type: ignore
    except ImportError as exc:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        candidate_paths = [
            Path("/usr/lib/python3/dist-packages"),
            Path(f"/usr/lib/python{version}/dist-packages"),
            Path(f"/usr/local/lib/python{version}/dist-packages"),
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                site.addsitedir(str(candidate))
        try:
            from gpiozero import Buzzer, LED, PWMOutputDevice  # type: ignore
        except ImportError as second_exc:
            raise RuntimeError(
                "gpiozero is not installed for this Python interpreter. Run `bash scripts/pi/setup_pi.sh` first."
            ) from second_exc
    return LED, Buzzer, PWMOutputDevice


class HardwareController:
    def __init__(
        self,
        buzzer_mode: str,
        buzzer_pin: int = BUZZER_GPIO_PIN,
        standby_reminder_seconds: float = DEFAULT_STANDBY_REMINDER_SECONDS,
    ) -> None:
        LED, Buzzer, PWMOutputDevice = import_gpiozero()
        self.leds = {name: LED(pin) for name, pin in LED_GPIO_PINS.items()}
        self.buzzer_mode = buzzer_mode
        self.buzzer_pin = buzzer_pin
        self.standby_reminder_seconds = standby_reminder_seconds
        self.last_standby_sound_at: float | None = None
        self.buzzer = None

        if buzzer_mode == "active":
            self.buzzer = Buzzer(buzzer_pin)
        elif buzzer_mode == "passive":
            self.buzzer = PWMOutputDevice(buzzer_pin, frequency=440.0)
            self.buzzer.off()

    def close(self) -> None:
        self.clear()
        if self.buzzer is not None:
            self.buzzer.off()
            self.buzzer.close()
        for led in self.leds.values():
            led.close()

    def clear(self) -> None:
        self.all_leds_off()
        if self.buzzer is not None:
            self.buzzer.off()

    def all_leds_off(self) -> None:
        for led in self.leds.values():
            led.off()

    def all_leds_on(self) -> None:
        for led in self.leds.values():
            led.on()

    def flash_all_leds(self, cycles: int, cycle_seconds: float) -> None:
        on_seconds = max(cycle_seconds / 2.0, 0.0)
        off_seconds = max(cycle_seconds - on_seconds, 0.0)
        for _ in range(cycles):
            for led in self.leds.values():
                led.on()
            time.sleep(on_seconds)
            self.all_leds_off()
            time.sleep(off_seconds)

    def indicate_boot(self) -> None:
        self.all_leds_on()
        self.play_sound("boot")
        self.all_leds_off()

    def indicate_category(self, category: str, hold_seconds: float) -> None:
        self.indicate_category_led(category)
        self.play_sound(category)

    def indicate_category_led(self, category: str) -> None:
        for name, led in self.leds.items():
            if name == category:
                led.on()
            else:
                led.off()

    def indicate_tracking(self) -> None:
        self.all_leds_on()

    def indicate_standby(self, reminder_interval_seconds: float | None = None) -> None:
        self.all_leds_off()
        interval = self.standby_reminder_seconds if reminder_interval_seconds is None else reminder_interval_seconds
        if interval <= 0:
            return

        now = time.monotonic()
        if self.last_standby_sound_at is not None and now - self.last_standby_sound_at < interval:
            return

        self.play_sound("standby")
        self.last_standby_sound_at = now

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
            self.buzzer.value = PASSIVE_BUZZER_LEVEL
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
