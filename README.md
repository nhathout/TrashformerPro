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
python scripts/inspect_garbage_dataset.py
```

The download script pulls `sumn2u/garbage-classification-v2` into `data/raw/garbage_v2`, and the inspection script prints image counts by source folder.

## Files Present So Far
- `scripts/pi/setup_pi.sh`: Raspberry Pi bootstrap script for package install, virtual environment setup, and runtime directory creation.
- `scripts/pi/test_cam.sh`: quick shell smoke test for the connected Pi Camera.
- `inference/pi/capture_img.py`: simple Python capture entry point that wraps `rpicam-still`.
- `runtime/captures/`: output folder for captured test images and Python-triggered captures.
- `scripts/download_garbage_dataset.sh`: Kaggle download helper for the base garbage dataset.
- `scripts/inspect_garbage_dataset.py`: dataset inspection utility that counts images by folder.
- `datasets/mappings/four_class_map.yaml`: class collapse map for the four TrashformerPro output categories.
- `docs/hardware/pi-camera/first_test.jpg`: first saved Pi Camera hardware test image.
- `docs/diagrams/trashformer-pro.drawio.pdf`: current project diagram export.
- `docs/midterm/TrashformerPro_quad_chart.pptx.pdf`: current midterm presentation export.

## Notes
- Run the Pi camera commands on Raspberry Pi OS with the camera stack enabled and `rpicam-still` available.
- The shell scripts do not need execute permissions if you invoke them with `bash ...`.
- `firmware/` and `training/` exist as placeholders for the next stages of the project.
