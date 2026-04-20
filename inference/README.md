# Raspberry Pi Inference

This document is about running the trained TrashformerPro classifier on the Raspberry Pi and preserving every real-world test image for later fine-tuning.

## What This Workflow Does

The default Pi workflow now uses `inference/pi/capture_and_classify.py`.

Each run:

1. captures a fresh image from the Pi camera
2. stores that image in `runtime/captures/`
3. runs classification with a trained checkpoint
4. appends a metadata row to `runtime/inference_records/predictions.csv`
5. writes a per-inference JSON file to `runtime/inference_records/json/`

That means every hardware test leaves behind reusable data for later labeling and fine-tuning.

## One-Time Pi Setup

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
```

Then install the model runtime dependencies:

```bash
pip install torch torchvision
```

Check that they installed correctly:

```bash
python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

## Put The Checkpoint On The Pi

The Pi scripts default to `models/best.pt`, with a fallback to `runtime/models/best.pt` if you want to keep the deployed checkpoint outside the tracked `models/` folder.

The simplest convention in this repo is:

```text
models/best.pt
```

If you want to copy it over SSH from another machine, a typical command looks like:

```bash
scp <path-to-best.pt> pi@<pi-host>:~/TrashformerPro/models/best.pt
```

If neither `models/best.pt` nor `runtime/models/best.pt` exists yet, you still need to train the model first. Use `training/README.md`.

## Verify The Camera

Run the shell-based camera test:

```bash
bash scripts/pi/test_cam.sh
```

That writes a test image into `runtime/captures/`.

## Capture The Empty-Plate Reference

The full Pi loop can detect "no object in frame" by comparing each new image against an empty-plate reference image.

Capture that reference after the camera position and lighting are stable:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

By default this writes:

```text
runtime/calibration/empty_plate.jpg
```

## Fastest Real-World Inference Loop

From the repo root on the Pi:

```bash
source .venv/bin/activate
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu
```

This is the default manual inference loop while bringing the hardware up.

If you want extra camera options, repeat `--camera-arg`. Example:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu \
  --camera-arg=--timeout \
  --camera-arg=1000
```

## Full System Runtime

Once manual inference looks reasonable, I'll move to the end-to-end Pi loop:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode active
```

With passive piezo buzzer:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive
```

Default behavior:

- startup sound on boot
- repeated latest-frame capture with a shared `2.0 s` stability gate
- blank-reference comparison using `runtime/calibration/empty_plate.jpg`
- mutually exclusive runtime states for `standby`, `tracking`, `classified`, `low_confidence`, `scene_error`, and `degraded`
- standby gives only an occasional reminder beep when no object is present or confidence is below threshold
- alert sound plus LED flashing when the plate / framing changes too much, or when runtime failures push the system into `degraded`
- the predicted class LED stays on when confidence clears the threshold
- a distinct buzzer pattern per class
- more playful boot/shutdown chirps when using a passive piezo buzzer
- shutdown sound on exit

Useful options:

- `--min-confidence 0.75`
- `--stable-hold-seconds 2.0`
- `--category-hold-seconds 2.0`
- `--standby-reminder-seconds 20`
- `--skip-presence-check`
- `--once`
- `--camera-arg=--timeout --camera-arg=1000`

The runner also writes event logs to:

```text
runtime/logs/full_system_events.jsonl
```

Each prediction record also stores the exact checkpoint path and SHA-256 fingerprint that produced it, so you can verify which `best.pt` was active during a run.

## Classify An Existing Saved Image

If you want to classify already-taken image without taking a new capture:

```bash
python inference/pi/classify_image.py \
  --image runtime/captures/<capture>.jpg \
  --checkpoint models/best.pt \
  --device cpu
```

By default, this also records metadata in `runtime/inference_records/`. If you explicitly do not want that for a one-off test, add:

```bash
--no-record
```

## Capture Without Classification

If you only want to save a new camera frame:

```bash
python inference/pi/capture_img.py
```

## What Gets Saved

### Images

- `runtime/captures/<timestamp>.jpg`

### Inference Manifest

- `runtime/inference_records/predictions.csv`

Important columns include:

- `image_path`
- `predicted_class`
- `predicted_confidence`
- `checkpoint_path`
- `confirmed_label`
- `notes`

### Per-Inference JSON

- `runtime/inference_records/json/<record_id>.json`

This stores the top-k predictions and the rest of the metadata in a machine-readable form.

## Collecting Fine-Tuning Data

The simplest workflow is:

1. keep using `capture_and_classify.py` or the full Pi runner during hardware tests
2. periodically review `runtime/inference_records/predictions.csv`
3. fill in `confirmed_label` after you verify the true class
4. add notes for bad lighting, occlusion, unusual objects, or hardware positioning issues
5. build combined fine-tuning manifests with `python training/prepare_runtime_feedback.py`
6. fine-tune from the deployed checkpoint with `python training/train_classifier.py --init-checkpoint models/best.pt ...`

If you already know the true class at capture time, you can store it immediately:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu \
  --confirmed-label plastic \
  --notes "clear bottle on white plate"
```

## Recommended Bring-Up Order

1. verify the camera with `bash scripts/pi/test_cam.sh`
2. copy `best.pt` to `models/best.pt`
3. run `python inference/pi/capture_and_classify.py --checkpoint models/best.pt --device cpu`
4. inspect real predictions on a handful of items
5. capture the empty reference with `/usr/bin/python3 scripts/pi/capture_empty_reference.py`
6. run `/usr/bin/python3 scripts/pi/full_system_runner.py --checkpoint models/best.pt --classifier-python .venv/bin/python`
7. keep collecting captures and prediction records while testing the full system
8. fill in `confirmed_label` for the captures you trust
9. run `python training/prepare_runtime_feedback.py`
10. fine-tune only after the failure cases become clear

## Important Note

The current model is a classifier, not a detector.

That is okay as long as:

- one object is present
- the object is centered consistently
- the plate/background stays reasonably controlled

If the hardware later needs cluttered-scene understanding, then a detection or segmentation stage may be worth adding. For the current prototype, classification-first is the right place to start.

The full-system runner handles "no object in frame" with an empty-plate calibration image. That is a practical prototype heuristic, not true object detection.
