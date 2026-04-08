# TrashformerPro

TrashformerPro is a smart trash can prototype that classifies one waste item at a time on a controlled plate, then routes it toward the correct bin.

Right now the repo is organized around one practical goal: get a baseline classifier working, validate it on real Raspberry Pi captures, and use those real captures to improve the model later.

## What Runs Where

- Raspberry Pi 5: camera capture, CPU inference, and future hardware control
- Windows 4080 PC: first baseline training runs
- BU SCC: optional later sweeps once the local baseline is already useful

## Current Approach

- Task: 4-class image classification
- Classes: `plastic`, `paper_cardboard`, `metal_glass`, `trash_other`
- Assumption: one object is centered on a clear or controlled plate
- Model family: transfer learning from ImageNet-pretrained torchvision backbones

This is a classification system, not an object detector. That is a good fit for the current hardware concept because you are placing a single item into a constrained camera view.

## Recommended Next Step

Now that the baseline exists, the highest-value next move is Pi validation, not more SCC sweeps.

Use the trained checkpoint on real Pi captures, see whether the real-world plate images are good enough, and only then decide whether you need more training or a different model.

## Quick Starts

### Raspberry Pi Inference

From the repo root on the Pi:

```bash
bash scripts/pi/setup_pi.sh
source .venv/bin/activate
pip install torch torchvision
python inference/pi/capture_and_classify.py \
  --checkpoint runtime/models/best.pt \
  --device cpu
```

Every `capture_and_classify.py` run:

- captures a fresh image into `runtime/captures/`
- prints the prediction to the terminal
- appends a metadata row to `runtime/inference_records/predictions.csv`
- writes a per-inference JSON record to `runtime/inference_records/json/`

Full Pi instructions: `inference/README.md`

### Windows Baseline Training

From the repo root on the Windows GPU machine:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\training\windows\setup_windows_gpu.ps1 -PythonLauncher python3.13.exe
.\training\windows\train_baseline.ps1
```

The best checkpoint will be written under `training/runs/<run_name>/best.pt`.

Full training instructions: `training/README.md`

### Dataset Download

If you need the Garbage V2 source dataset locally:

```bash
bash scripts/download_garbage_dataset.sh
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

The dataset is expected under `data/raw/garbage_v2`.

## Repo Guide

- `README.md`: project overview and quick starts
- `docs/hardware/README.md`: Raspberry Pi 5 wiring and non-motor hardware bring-up
- `inference/README.md`: Raspberry Pi capture and inference workflow
- `scripts/pi/README.md`: Pi quick start for setup, hardware tests, and moving captures back to a laptop
- `training/README.md`: dataset prep, Windows training, and optional SCC usage
- `inference/pi/`: Pi capture and inference scripts
- `training/`: model training, dataset manifest prep, and environment checks
- `scripts/pi/`: Pi setup and camera test helpers

## Practical Workflow

1. Train the first baseline on the Windows 4080 PC.
2. Copy `best.pt` onto the Pi, usually into `runtime/models/`.
3. Use `python inference/pi/capture_and_classify.py --checkpoint runtime/models/best.pt --device cpu`.
4. Review real predictions and keep collecting captures.
5. When needed, label the archived Pi captures and fine-tune on that data.
6. Only after the on-device loop is useful, spend time on SCC comparisons or longer sweeps.

## Notes

- The repo currently treats `clothes` and `shoes` as `trash_other` because the prototype exposes four bins.
- Runtime outputs such as captures, inference records, and training runs are generated locally and should stay out of commits.
- The Pi-side inference workflow is designed to leave behind reusable data every time you test on hardware.
