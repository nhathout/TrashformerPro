# Hardware Bring-Up

This document covers the first non-motor hardware bring-up for TrashformerPro:

- 4 status LEDs
- a buzzer
- an ESP32 dev board

The goal is to get each component working safely from the Raspberry Pi 5 before you start integrating the motors.

## Wiring Plan

The Pi-side scripts in `scripts/pi/` use this default BCM pin map:

| Component | BCM GPIO | Physical pin on Pi 5 |
| --- | --- | --- |
| LED 1 `plastic` | `GPIO17` | pin `11` |
| LED 2 `paper_cardboard` | `GPIO27` | pin `13` |
| LED 3 `metal_glass` | `GPIO22` | pin `15` |
| LED 4 `trash_other` | `GPIO23` | pin `16` |
| Buzzer signal | `GPIO24` | pin `18` |
| Ground rail | `GND` | pin `6` recommended |

For the LEDs, use one resistor per LED. A `220` to `330` ohm resistor is a good default.

For the ESP32, the safest first test is USB serial only. Do not wire the ESP32 directly to the Pi GPIO yet.

## Important Safety Notes

- Raspberry Pi GPIO is `3.3V` only. Do not put `5V` on a GPIO pin.
- Use a resistor on every LED.
- Do not connect motors directly to the Pi GPIO.
- Only connect the buzzer directly to a GPIO pin if it is a small `3.3V` active buzzer or a passive piezo buzzer. If your buzzer is marked `5V`, has a built-in driver board, or draws more than a few milliamps, stop and use a transistor driver later instead.
- For the ESP32, use USB for bring-up. That avoids power and logic-level mistakes.

These cautions line up with Raspberry Pi's GPIO documentation, which warns to use resistors with LEDs, avoid `5V` on `3.3V` GPIO, and not drive motors directly from GPIO: https://www.raspberrypi.com/documentation/hardware/hardware/raspberrypi/bcm2835/raspberry-pi-5.html

## Step-By-Step Wiring

### 1. Set Up A Ground Rail

1. Power the Pi off.
2. Put your breadboard next to the Pi.
3. Run one jumper wire from Raspberry Pi physical pin `6` (`GND`) to the breadboard ground rail.

You can use another ground pin later if the wire routing is cleaner, but pin `6` is a simple starting point.

### 2. Wire LED 1

1. Place LED 1 on the breadboard.
2. Connect the LED short leg, the cathode, to the breadboard ground rail.
3. Connect the LED long leg, the anode, to one side of a resistor.
4. Connect the other side of that resistor to Raspberry Pi physical pin `11` (`GPIO17`).

This LED is the `plastic` indicator in the scripts.

### 3. Wire LED 2

Repeat the same pattern:

1. LED short leg to ground rail.
2. LED long leg to resistor.
3. Resistor to Raspberry Pi physical pin `13` (`GPIO27`).

This LED is the `paper_cardboard` indicator.

### 4. Wire LED 3

Repeat the same pattern:

1. LED short leg to ground rail.
2. LED long leg to resistor.
3. Resistor to Raspberry Pi physical pin `15` (`GPIO22`).

This LED is the `metal_glass` indicator.

### 5. Wire LED 4

Repeat the same pattern:

1. LED short leg to ground rail.
2. LED long leg to resistor.
3. Resistor to Raspberry Pi physical pin `16` (`GPIO23`).

This LED is the `trash_other` indicator.

### 6. Wire The Buzzer

Only do this direct wiring if the buzzer is a small `3.3V` buzzer or passive piezo.

For a simple 2-pin buzzer:

1. Connect the buzzer negative pin to the breadboard ground rail.
2. Connect the buzzer positive pin to Raspberry Pi physical pin `18` (`GPIO24`).

If your buzzer is a 3-pin module with labels like `VCC`, `GND`, and `SIG`, do not guess. Check the module labeling first. Many of those modules want a supply pin rather than direct GPIO drive.

### 7. Connect The ESP32

For the first test, do not use jumper wires between the ESP32 and Pi.

1. Plug the ESP32 dev board into one of the Pi's USB ports with its normal USB cable.
2. Let the ESP32 power from USB.
3. The Pi should expose it as a serial device such as `/dev/ttyUSB0` or `/dev/ttyACM0`.

This USB-first approach is much safer than direct UART wiring while you are still bringing the system up.

## Install The Pi-Side Test Dependencies

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
```

That installs:

- camera helpers already used by the repo
- `python3-gpiozero` for LED and buzzer tests
- `python3-serial` for the ESP32 serial test

## Run The LED Test

From the repo root on the Pi:

```bash
python3 scripts/pi/test_leds.py
```

What to expect:

- each LED lights one at a time
- then all four light together briefly

If one LED does not light:

- flip that LED around
- re-check the resistor and jumper placement
- confirm you used the intended physical pin

## Run The Buzzer Test

If your buzzer is an active buzzer:

```bash
python3 scripts/pi/test_buzzer.py --mode active
```

If your buzzer is a passive piezo buzzer:

```bash
python3 scripts/pi/test_buzzer.py --mode passive
```

## Flash The ESP32 Test Firmware

The repo now includes a simple Arduino sketch:

- `firmware/esp32/serial_heartbeat/serial_heartbeat.ino`

It does three things:

1. prints `esp32-ready` on boot
2. replies `pong` when it receives `ping`
3. emits a `heartbeat:<millis>` line every two seconds

The serial behavior is based on Espressif's official Arduino-ESP32 `Serial` API: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html

Flash it with the Arduino IDE:

1. Open Arduino IDE on your development machine.
2. Open `firmware/esp32/serial_heartbeat/serial_heartbeat.ino`.
3. Select your ESP32 board.
4. Select the ESP32 serial port.
5. Upload the sketch.

## Run The ESP32 Test From The Pi

Once the ESP32 is connected to the Pi over USB:

```bash
python3 scripts/pi/test_esp32_serial.py --list
python3 scripts/pi/test_esp32_serial.py
```

What success looks like:

- the script finds a serial port
- it sends `ping`
- the ESP32 answers `pong`
- then you see heartbeat lines for a few seconds

## Suggested Bring-Up Order

1. wire the four LEDs
2. run `python3 scripts/pi/test_leds.py`
3. wire the buzzer
4. run `python3 scripts/pi/test_buzzer.py --mode active` or `--mode passive`
5. flash the ESP32 test sketch
6. plug the ESP32 into the Pi over USB
7. run `python3 scripts/pi/test_esp32_serial.py`

## Later

After these tests pass, the next reasonable layer is:

1. define one shared hardware pin map for the final program
2. decide whether the ESP32 will handle only motor control or also status outputs
3. add motor-driver wiring rather than direct GPIO motor control

For now, this guide intentionally stops before motors.
