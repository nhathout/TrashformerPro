# Pi Script Quick Start

## Scripts In This Folder

- `scripts/pi/setup_pi.sh`: installs Pi-side packages and creates runtime folders
- `scripts/pi/test_cam.sh`: captures one camera image into `runtime/captures/`
- `scripts/pi/capture_empty_reference.py`: captures the empty-plate reference image used by the full runner
- `scripts/pi/full_system_runner.py`: runs the end-to-end Pi loop with capture, classification, LEDs, and buzzer output
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
- `runtime/calibration/`
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

### 4. Capture The Empty Reference

Once the camera position is fixed, capture the empty plate with normal lighting:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

That writes:

```text
runtime/calibration/empty_plate.jpg
```

### 5. Full System Runner

After you have a trained checkpoint in `models/best.pt` and `torch` installed in `.venv`, run:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode active
```

If you have a passive piezo buzzer and want the softer Windows-inspired boot/shutdown chimes plus distinct category tones:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive
```

The runner uses:

- system Python for GPIO and OpenCV
- `.venv/bin/python` for the classifier subprocess

That split keeps GPIO support simple while still letting the model run in the virtual environment that has `torch`.

At startup, the runner prints the exact checkpoint path plus a short SHA-256 prefix so you can confirm which `best.pt` file is active.

### 6. ESP32 USB Serial Test

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

## Model Location

The Pi scripts now default to `models/best.pt`, with a fallback to `runtime/models/best.pt` if needed. If you want to replace the deployed model, copy your selected checkpoint into one of those locations and pass `--checkpoint` explicitly if you want zero ambiguity.

Example copy command:

```bash
scp /path/to/best.pt <pi-user>@<pi-host>:~/TrashformerPro/models/best.pt
```

Then on the Pi:

```bash
source .venv/bin/activate
pip install torch torchvision
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu
```

For the full system loop, also capture the empty reference and then run:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python
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
8. train and copy `best.pt` to `models/best.pt`
9. `/usr/bin/python3 scripts/pi/capture_empty_reference.py`
10. `/usr/bin/python3 scripts/pi/full_system_runner.py --checkpoint models/best.pt --classifier-python .venv/bin/python`

That gives you camera, indicators, model inference, and the end-to-end output loop before you move on to motors.

## Relabel And Fine-Tune Stored Captures

Every inference already saves:

- the image in `runtime/captures/`
- the prediction record in `runtime/inference_records/predictions.csv`

To build a fine-tuning set from Pi mistakes:

1. Open `runtime/inference_records/predictions.csv`.
2. For each image you want to use, fill in `confirmed_label` with the true class:
   `plastic`, `paper_cardboard`, `metal_glass`, or `trash_other`.
3. Add optional notes in the `notes` column.
4. Build combined manifests:

```bash
python training/prepare_runtime_feedback.py
```

5. Fine-tune from the current deployed checkpoint:

```bash
python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/runtime_feedback/train.csv \
  --val-manifest datasets/manifests/four_class/runtime_feedback/val.csv \
  --test-manifest datasets/manifests/four_class/runtime_feedback/test.csv \
  --model mobilenet_v3_large \
  --device cpu \
  --init-checkpoint models/best.pt
```

That keeps the original dataset in the training mix while adding the confirmed Pi captures on top.
