# TrashformerPro

TrashformerPro is a smart trash can prototype that classifies one waste item at a time on a controlled plate, then routes it toward the correct bin.

## Current Status

- The repo already has dataset prep, model training, Pi inference, and separate hardware test scripts.
- The repo currently includes a deployed checkpoint at `models/best.pt`.
- If you want a newer checkpoint, train one and either overwrite `models/best.pt` or pass a different `--checkpoint` path explicitly.

## What Runs Where

- Raspberry Pi 5: camera capture, CPU inference, LEDs, buzzer, and the full runtime loop
- Mac: optional local training on `mps` or `cpu`
- Windows 4080 PC: fastest local baseline training
- BU SCC: optional later sweeps once the local baseline already works

## Current Approach

- Task: 4-class image classification
- Classes: `plastic`, `paper_cardboard`, `metal_glass`, `trash_other`
- Assumption: one object is centered on a controlled plate
- Model family: transfer learning from ImageNet-pretrained torchvision backbones

## Recommended Order

1. Train the first real checkpoint on the Windows 4080 PC or on your Mac.
2. Copy `best.pt` to `models/best.pt` on the Pi.
3. Validate manual Pi inference on a few real objects.
4. Capture an empty-plate reference image.
5. Run the full Pi loop with LEDs and buzzer enabled.
6. Collect real failures and relabel them for fine-tuning.
7. Add motors only after the perception-and-indicator loop is stable.

## Quick Starts

### Windows 4080 Training

From the repo root on the Windows GPU machine:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\training\windows\setup_windows_gpu.ps1 -PythonLauncher python3.13.exe
.\training\windows\train_baseline.ps1
```

The best checkpoint is written under `training/runs/<run_name>/best.pt`.

### Mac Training

From the repo root on the Mac:

```bash
bash training/mac/setup_mac_training.sh
bash training/mac/train_baseline.sh
```

The Mac training script auto-selects `mps` when available and otherwise falls back to `cpu`.

### Raspberry Pi Manual Inference

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
pip install torch torchvision
python inference/pi/capture_and_classify.py \
  --checkpoint models/best.pt \
  --device cpu
```

Every `capture_and_classify.py` run:

- captures a fresh image into `runtime/captures/`
- prints the prediction to the terminal
- appends a metadata row to `runtime/inference_records/predictions.csv`
- writes a per-inference JSON record to `runtime/inference_records/json/`

### Raspberry Pi Full System Loop

Capture the empty plate first:

```bash
/usr/bin/python3 scripts/pi/capture_empty_reference.py
```

Then run the full loop:

```bash
/usr/bin/python3 scripts/pi/full_system_runner.py \
  --checkpoint models/best.pt \
  --classifier-python .venv/bin/python \
  --buzzer-mode active
```

If you have a passive piezo buzzer and want the more distinct tone patterns, use `--buzzer-mode passive`.

The full runner:

- plays a startup sound on boot
- captures images continuously
- returns to a neutral standby tone when no object is detected or confidence is too low
- flashes all LEDs only for actual runtime failures
- lights the predicted class LED when confidence is high enough
- plays a different buzzer pattern for each class
- plays a shutdown sound when you stop the program

## Dataset Download

If you need the Garbage V2 source dataset locally:

```bash
bash scripts/download_garbage_dataset.sh
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

The dataset is expected under `data/raw/garbage_v2`.

## Repo Guide

- `README.md`: project overview and quick-start order
- `training/README.md`: dataset prep plus Windows, Mac, and SCC training workflows
- `inference/README.md`: Pi inference, empty-frame calibration, and full runtime loop
- `scripts/pi/README.md`: Pi hardware bring-up and final runner usage
- `docs/hardware/README.md`: wiring and non-motor hardware bring-up
- `training/`: model training, dataset manifests, and environment checks
- `inference/pi/`: capture and classifier scripts
- `scripts/pi/`: Pi setup, calibration, hardware tests, and the full system runner

## Practical Workflow

1. Train the first baseline on the Windows 4080 PC or on your Mac.
2. Copy `best.pt` onto the Pi, usually into `models/best.pt`.
3. Use `python inference/pi/capture_and_classify.py --checkpoint models/best.pt --device cpu`.
4. Capture the empty reference with `/usr/bin/python3 scripts/pi/capture_empty_reference.py`.
5. Run `/usr/bin/python3 scripts/pi/full_system_runner.py --checkpoint models/best.pt --classifier-python .venv/bin/python`.
6. Review real predictions and keep collecting captures.
7. Fill in `confirmed_label` in `runtime/inference_records/predictions.csv`.
8. Run `python training/prepare_runtime_feedback.py` and fine-tune with `--init-checkpoint models/best.pt`.
9. Only after the on-device loop is useful, spend time on SCC sweeps or motors.

## Notes

- The repo currently treats `clothes` and `shoes` as `trash_other` because the prototype exposes four bins.
- Runtime outputs such as captures, inference records, logs, and training runs are generated locally and should stay out of commits.
- The Pi-side inference workflow is designed to leave behind reusable data every time you test on hardware.
