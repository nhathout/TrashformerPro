# Hardware Bring-Up

This guide covers the hardware included in the final prototype:

- four category LEDs
- buzzer feedback
- optional ESP32 USB serial smoke test

The motorized tilting mechanism is not implemented in the final repo. Motor wiring, motor-driver selection, ESP32 motor firmware, and the mechanical tilt loop are future work.

## Default Pin Map

| Component | BCM GPIO | Physical pin on Pi 5 |
| --- | --- | --- |
| LED 1 `plastic` | `GPIO17` | pin `11` |
| LED 2 `paper_cardboard` | `GPIO27` | pin `13` |
| LED 3 `metal_glass` | `GPIO22` | pin `15` |
| LED 4 `trash_other` | `GPIO23` | pin `16` |
| Buzzer signal | `GPIO24` | pin `18` |
| Ground rail | `GND` | pin `6` recommended |

Use one `220` to `330` ohm resistor per LED.

## Safety Notes

- Raspberry Pi GPIO is `3.3V` only.
- Do not put `5V` on a GPIO pin.
- Use a resistor on every LED.
- Do not connect motors directly to Pi GPIO.
- Use a motor driver for any future motor work.
- Only connect a buzzer directly to GPIO if it is a small `3.3V` active buzzer or passive piezo.
- Bring up the ESP32 over USB first instead of direct UART wiring.

Raspberry Pi GPIO reference: https://www.raspberrypi.com/documentation/hardware/hardware/raspberrypi/bcm2835/raspberry-pi-5.html

## Wiring

Ground:

1. Power the Pi off.
2. Connect Pi physical pin `6` (`GND`) to the breadboard ground rail.

LEDs:

1. Put the LED cathode, the short leg, on the ground rail.
2. Connect the LED anode, the long leg, to one side of a resistor.
3. Connect the other side of the resistor to the assigned Pi GPIO pin.

Repeat for all four LEDs using the default pin map.

Buzzer:

1. Confirm the buzzer is safe for direct `3.3V` GPIO signaling.
2. Connect the negative pin to ground.
3. Connect the positive or signal pin to physical pin `18` (`GPIO24`).

ESP32:

1. Connect the ESP32 to the Pi with USB.
2. Do not wire ESP32 GPIO directly to Pi GPIO during first bring-up.
3. The Pi should expose the board as `/dev/ttyUSB0` or `/dev/ttyACM0`.

## Install Test Dependencies

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
```

This installs camera helpers, `gpiozero`, and serial tooling used by the smoke tests.

## Hardware Tests

LEDs:

```bash
python3 scripts/pi/test_leds.py
```

Buzzer:

```bash
python3 scripts/pi/test_buzzer.py --mode passive
```

Use `--mode active` for an active buzzer.

ESP32 serial:

```bash
python3 scripts/pi/test_esp32_serial.py --list
python3 scripts/pi/test_esp32_serial.py
```

## ESP32 Test Firmware

The optional Arduino smoke-test sketch is:

```text
firmware/esp32/serial_heartbeat/serial_heartbeat.ino
```

It prints `esp32-ready`, responds to `ping` with `pong`, and emits a heartbeat line every two seconds.

## Final Prototype Hardware Scope

Implemented:

- Pi camera workflow
- LED class indicators
- buzzer feedback
- runtime state mirroring from the app or robot-only loop
- ESP32 USB serial test path

Future work:

- motor-driver wiring
- ESP32 or Pi motor-control ownership decision
- tilt-position sensing
- class-to-bin routing logic
- safety checks around moving parts