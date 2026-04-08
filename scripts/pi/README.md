# Pi Script Quick Start

## Scripts In This Folder

- `scripts/pi/setup_pi.sh`: installs Pi-side packages and creates runtime folders
- `scripts/pi/test_cam.sh`: captures one camera image into `runtime/captures/`
- `scripts/pi/test_leds.py`: cycles the four class-status LEDs
- `scripts/pi/test_buzzer.py`: tests an active buzzer or passive piezo buzzer
- `scripts/pi/test_esp32_serial.py`: checks USB serial communication with the ESP32

## One-Time Pi Setup

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
```

That creates:

- `runtime/captures/`
- `runtime/models/`
- `runtime/inference_records/`

## Important Python Note

For the hardware tests in `scripts/pi/`, use the system interpreter:

```bash
/usr/bin/python3
```

Reason: `setup_pi.sh` installs `gpiozero` and `pyserial` with `apt`, so those packages are available to the system Python immediately. If you activate `.venv` first and then run the hardware tests with `python` or `python3`, you may get missing-module errors.

If that happens, either run `deactivate` first or call `/usr/bin/python3` explicitly.

## What You Can Run Today

### 1. Camera Test

Capture one image:

```bash
bash scripts/pi/test_cam.sh
```

The image will be written to:

```text
runtime/captures/test_<timestamp>.jpg
```

List the newest captures:

```bash
ls -lt runtime/captures
```

### 2. LED Test

Run the default LED sequence:

```bash
/usr/bin/python3 scripts/pi/test_leds.py
```

Useful shorter test:

```bash
/usr/bin/python3 scripts/pi/test_leds.py --cycles 1 --hold-seconds 1.0
```

Default GPIO map:

- `plastic`: `GPIO17` / physical pin `11`
- `paper_cardboard`: `GPIO27` / physical pin `13`
- `metal_glass`: `GPIO22` / physical pin `15`
- `trash_other`: `GPIO23` / physical pin `16`

### 3. Buzzer Test

For an active buzzer:

```bash
/usr/bin/python3 scripts/pi/test_buzzer.py --mode active
```

For a passive piezo buzzer:

```bash
/usr/bin/python3 scripts/pi/test_buzzer.py --mode passive
```

Default buzzer pin:

- `GPIO24` / physical pin `18`

### 4. ESP32 USB Serial Test

First list candidate serial ports:

```bash
/usr/bin/python3 scripts/pi/test_esp32_serial.py --list
```

Then run the handshake test:

```bash
/usr/bin/python3 scripts/pi/test_esp32_serial.py
```

If the script does not receive `pong`, flash the included test sketch first:

```text
firmware/esp32/serial_heartbeat/serial_heartbeat.ino
```

That sketch prints `esp32-ready`, answers `ping` with `pong`, and emits heartbeat lines so the Pi-side serial test has something predictable to read.

## How To Copy A Captured Image Back To Your Laptop

The simplest workflow is to pull the file from your laptop with `scp`. That way only the Pi needs SSH enabled.

1. On the Pi, capture an image:

```bash
bash scripts/pi/test_cam.sh
ls -lt runtime/captures
```

2. On your laptop, copy one image down:

```bash
scp <pi-user>@raspberrypi.local:~/TrashformerPro/runtime/captures/test_<timestamp>.jpg ~/Downloads/
```

If `raspberrypi.local` does not resolve, find the Pi IP address:

```bash
hostname -I
```

Then use that IP in the `scp` command instead:

```bash
scp <pi-user>@<pi-ip>:~/TrashformerPro/runtime/captures/test_<timestamp>.jpg ~/Downloads/
```

If you want the whole capture folder instead of one file:

```bash
scp -r <pi-user>@<pi-host>:~/TrashformerPro/runtime/captures ~/Downloads/trashformer_captures
```

## Tomorrow: Bring The Model Over

Once you have the trained checkpoint on your laptop or PC, copy it to the Pi:

```bash
scp /path/to/best.pt <pi-user>@<pi-host>:~/TrashformerPro/runtime/models/best.pt
```

Then on the Pi:

```bash
source .venv/bin/activate
pip install torch torchvision
python inference/pi/capture_and_classify.py \
  --checkpoint runtime/models/best.pt \
  --device cpu
```

If you only want to capture an image inside the inference workflow without classifying yet:

```bash
python inference/pi/capture_img.py
```

## Suggested Order For Your Current Setup

Since your camera and LEDs are already connected:

1. `bash scripts/pi/setup_pi.sh`
2. `bash scripts/pi/test_cam.sh`
3. `/usr/bin/python3 scripts/pi/test_leds.py`
4. `/usr/bin/python3 scripts/pi/test_buzzer.py --mode active` or `--mode passive`
5. flash `firmware/esp32/serial_heartbeat/serial_heartbeat.ino`
6. `/usr/bin/python3 scripts/pi/test_esp32_serial.py --list`
7. `/usr/bin/python3 scripts/pi/test_esp32_serial.py`
8. pull the saved image back to your laptop with `scp`

That gives you camera, indicators, and USB serial confidence before you move on to model deployment.
