# TrashformerPro
A smart trash can that classifies waste items into one of four categories/internal compartments. The waste item is placed on a central plate, which mechanically tilts and dumps based on the visual classification.

## Quick Start

1. On the Raspberry Pi 5, from the repo root, run:

```bash
bash scripts/pi/setup_pi.sh
```

This script updates the system, installs `git`, `python3-venv`, and `python3-opencv`, creates local runtime folders, creates `.venv` if needed, and upgrades `pip`.

2. Activate the virtual environment:

```bash
source .venv/bin/activate
```

3. Verify that the Pi Camera is detected and save a shell-based test image:

```bash
bash scripts/pi/test_cam.sh
```

This uses `rpicam-hello --list-cameras` and `rpicam-still`, then writes a timestamped image to `runtime/captures/`.

4. Capture an image from Python:

```bash
python inference/pi/capture_img.py
```

This also saves a timestamped `.jpg` to `runtime/captures/`.

5. If you want the training dataset locally, configure the Kaggle CLI first, then run:

```bash
bash scripts/download_garbage_dataset.sh
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

The download script pulls `sumn2u/garbage-classification-v2` into `data/raw/garbage_v2`. The inspection script reports counts for a single variant so the same example is not triple-counted across `original`, `standardized_256`, and `standardized_384`.

6. Create the reproducible four-class train/validation/test manifests:

```bash
python training/prepare_dataset.py --variant standardized_256 --seed 42
```

7. Train the first transfer-learning baseline on your GPU machine, not on the Raspberry Pi:

```bash
# Windows 4080 PC
powershell -ExecutionPolicy Bypass -File training/windows/setup_windows_gpu.ps1
powershell -ExecutionPolicy Bypass -File training/windows/train_baseline.ps1

# BU SCC
bash training/scc/setup_scc_env.sh /projectnb/<project> /projectnb/<project>/TrashformerPro python3/3.10.12
qsub training/scc/train_baseline.qsub
```

8. Move the trained checkpoint to the Pi and classify a captured image:

```bash
python inference/pi/classify_image.py \
  --image runtime/captures/<capture>.jpg \
  --checkpoint training/runs/<run_name>/best.pt \
  --device cpu
```

For the full modeling workflow and report checklist, see `training/README.md`.

## Files Present So Far
- `scripts/pi/setup_pi.sh`: Raspberry Pi bootstrap script for package install, virtual environment setup, and runtime directory creation.
- `scripts/pi/test_cam.sh`: quick shell smoke test for the connected Pi Camera.
- `inference/pi/capture_img.py`: simple Python capture entry point that wraps `rpicam-still`.
- `inference/pi/classify_image.py`: single-image inference entry point for a trained TrashformerPro classifier.
- `runtime/captures/`: output folder for captured test images and Python-triggered captures.
- `scripts/download_garbage_dataset.sh`: Kaggle download helper for the base garbage dataset.
- `scripts/inspect_garbage_dataset.py`: dataset inspection utility that reports counts for one dataset variant and the collapsed four-class totals.
- `datasets/mappings/four_class_map.yaml`: class collapse map for the four TrashformerPro output categories.
- `datasets/manifests/four_class/standardized_256/`: reproducible train/val/test CSV manifests and a split summary for the four-class task.
- `training/prepare_dataset.py`: manifest builder for the four-class TrashformerPro training task.
- `training/train_classifier.py`: PyTorch transfer-learning training entry point.
- `training/verify_environment.py`: environment check for Python, Torch, and device visibility.
- `training/requirements.txt`: non-PyTorch training dependency list used by the setup scripts.
- `training/windows/setup_windows_gpu.ps1`: Windows 4080 virtualenv and CUDA PyTorch setup.
- `training/windows/train_baseline.ps1`: Windows baseline training helper.
- `training/scc/setup_scc_env.sh`: SCC virtualenv setup helper.
- `training/scc/run_baseline.sh`: SCC runtime wrapper invoked inside the batch job.
- `training/README.md`: step-by-step Windows and SCC training workflow plus final-report checklist.
- `training/scc/train_baseline.qsub`: starter BU SCC batch script.
- `docs/hardware/pi-camera/first_test.jpg`: first saved Pi Camera hardware test image.
- `docs/diagrams/trashformer-pro.drawio.pdf`: current project diagram export.
- `docs/midterm/TrashformerPro_quad_chart.pptx.pdf`: current midterm presentation export.

## Notes
- Run the Pi camera commands on Raspberry Pi OS with the camera stack enabled and `rpicam-still` available.
- The shell scripts do not need execute permissions if you invoke them with `bash ...`.
- Use the MacBook for code and inspection, the 4080 PC for the first real training runs, and BU SCC for larger sweeps or comparison experiments.
- The current four-class prototype maps `clothes` and `shoes` into `trash_other` because the hardware design only exposes four bins right now.
