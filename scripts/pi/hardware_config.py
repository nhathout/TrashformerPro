from __future__ import annotations

LED_GPIO_PINS = {
    "plastic": 17,
    "paper_cardboard": 27,
    "metal_glass": 22,
    "trash_other": 23,
}

BUZZER_GPIO_PIN = 24

GPIO_TO_PHYSICAL_PIN = {
    17: 11,
    27: 13,
    22: 15,
    23: 16,
    24: 18,
}

GROUND_PHYSICAL_PINS = (6, 9, 14, 20, 25, 30, 34, 39)
DEFAULT_LED_RESISTOR_OHMS = "220-330"
DEFAULT_SERIAL_BAUD = 115200
