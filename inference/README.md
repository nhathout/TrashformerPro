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

If your Pi image is not already configured for piwheels, retry with:

```bash
pip install torch torchvision --extra-index-url https://www.piwheels.org/simple
```

You can sanity-check the runtime with:

```bash
python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__)"
```

## Put The Checkpoint On The Pi

Create the model directory if needed:

```bash
mkdir -p runtime/models
```

Then copy your trained checkpoint into it. A common convention is:

```text
runtime/models/best.pt
```

If you want to copy it over SSH from another machine, a typical command looks like:

```bash
scp <path-to-best.pt> pi@<pi-host>:~/TrashformerPro/runtime/models/best.pt
```

## Verify The Camera

Run the shell-based camera test:

```bash
bash scripts/pi/test_cam.sh
```

That writes a test image into `runtime/captures/`.

## Fastest Real-World Inference Loop

From the repo root on the Pi:

```bash
source .venv/bin/activate
python inference/pi/capture_and_classify.py \
  --checkpoint runtime/models/best.pt \
  --device cpu
```

This is the command you should treat as the default manual inference loop while bringing the hardware up.

If you want extra camera options, repeat `--camera-arg`. Example:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint runtime/models/best.pt \
  --device cpu \
  --camera-arg=--timeout \
  --camera-arg=1000
```

## Classify An Existing Saved Image

If you already have an image and want to classify it without taking a new capture:

```bash
python inference/pi/classify_image.py \
  --image runtime/captures/<capture>.jpg \
  --checkpoint runtime/models/best.pt \
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

1. keep using `capture_and_classify.py` during hardware tests
2. periodically review `runtime/inference_records/predictions.csv`
3. fill in `confirmed_label` after you verify the true class
4. add notes for bad lighting, occlusion, unusual objects, or hardware positioning issues
5. use the saved images plus confirmed labels to build a real plate-image fine-tuning set later

If you already know the true class at capture time, you can store it immediately:

```bash
python inference/pi/capture_and_classify.py \
  --checkpoint runtime/models/best.pt \
  --device cpu \
  --confirmed-label plastic \
  --notes "clear bottle on white plate"
```

## Recommended Bring-Up Order

1. verify the camera with `bash scripts/pi/test_cam.sh`
2. copy `best.pt` to `runtime/models/best.pt`
3. run `python inference/pi/capture_and_classify.py --checkpoint runtime/models/best.pt --device cpu`
4. inspect real predictions on a handful of items
5. start integrating the hardware mechanism
6. keep collecting captures and prediction records while testing the full system
7. fine-tune only after the failure cases become clear

## Important Note

The current model is a classifier, not a detector.

That is okay as long as:

- one object is present
- the object is centered consistently
- the plate/background stays reasonably controlled

If the hardware later needs cluttered-scene understanding, then a detection or segmentation stage may be worth adding. For the current prototype, classification-first is the right place to start.
