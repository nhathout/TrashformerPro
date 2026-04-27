# Raspberry Pi Inference

This guide covers running the trained classifier on the Raspberry Pi and saving real hardware captures for later review.

## One-Time Pi Setup

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
pip install torch torchvision
```

Check the install:

```bash
python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

## Checkpoint Location

The default deployed checkpoint is:

```text
models/best.pt
```

Copy a trained checkpoint to the Pi with a command like:

```bash
scp <path-to-best.pt> pi@<pi-host>:~/TrashformerPro/models/best.pt
```

If `models/best.pt` does not exist yet, train a model first using `training/README.md`.

## Camera Check

```bash
bash scripts/pi/test_cam.sh
```

The test writes an image into `runtime/captures/`.

## Empty-Plate Calibration

Capture the reference image after the camera, plate, and lighting are in their demo positions:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Default output:

```text
runtime/calibration/empty_plate.jpg
```

The full runtime uses this image to distinguish an empty plate from a staged object.

## Manual Capture And Classification

```bash
source .venv/bin/activate
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu
```

Each run:

- captures a fresh image
- saves it in `runtime/captures/`
- prints the prediction
- appends a row to `runtime/inference_records/predictions.csv`
- writes a JSON record to `runtime/inference_records/json/`

Optional camera arguments can be passed through with repeated `--camera-arg` flags:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu \
  --camera-arg=--timeout \
  --camera-arg=1000
```

## Full System Runtime

Robot-only runtime:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode passive
```

Use `--buzzer-mode active` for an active buzzer.

Runtime behavior:

- plays a startup sound
- captures repeated live frames
- compares frames against `runtime/calibration/empty_plate.jpg`
- waits for the object to remain stable before classifying
- lights the predicted class LED when confidence passes the threshold
- plays a class-specific buzzer pattern
- records prediction and event logs
- returns to standby when no object is present

Useful options:

- `--min-confidence 0.75`
- `--stable-hold-seconds 2.0`
- `--category-hold-seconds 2.0`
- `--standby-reminder-seconds 20`
- `--skip-presence-check`
- `--once`
- `--camera-arg=--timeout --camera-arg=1000`

Runtime event log:

```text
runtime/logs/full_system_events.jsonl
```

## Classify An Existing Image

```bash
python inference/pi/classify_image.py \
  --image runtime/captures/<capture>.jpg \
  --checkpoint models/best.pt \
  --device cpu
```

Add `--no-record` for one-off tests that should not be written to the prediction log.

## Capture Without Classification

```bash
python inference/pi/capture_img.py
```

## Saved Data

Images:

```text
runtime/captures/<timestamp>.jpg
```

Prediction CSV:

```text
runtime/inference_records/predictions.csv
```

Important columns:

- `image_path`
- `predicted_class`
- `predicted_confidence`
- `checkpoint_path`
- `confirmed_label`
- `notes`

Per-inference JSON:

```text
runtime/inference_records/json/<record_id>.json
```

## Fine-Tuning Data Loop

1. Run manual inference or the full Pi runtime.
2. Review `runtime/inference_records/predictions.csv`.
3. Fill in `confirmed_label` for verified captures.
4. Add notes for lighting, occlusion, framing, or unusual objects.
5. Run `python training/prepare_runtime_feedback.py`.
6. Fine-tune with `python training/train_classifier.py --init-checkpoint models/best.pt ...`.

Known true labels can also be recorded at capture time:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu \
  --confirmed-label plastic \
  --notes "clear bottle on white plate"
```

## Prototype Assumptions

The current model is a classifier, not a detector. It works best when one object is centered on a controlled plate. Empty-plate comparison is a prototype heuristic and not a replacement for detection or segmentation.