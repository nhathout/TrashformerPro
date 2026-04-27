# Training Workflow

This guide covers dataset preparation, baseline training, and optional fine-tuning from real Pi captures.

## Baseline Configuration

- Task: 4-class image classification
- Classes: `plastic`, `paper_cardboard`, `metal_glass`, `trash_other`
- Dataset variant: `standardized_256`
- Model: `mobilenet_v3_large`
- Initialization: ImageNet pretrained weights
- Optimizer: `AdamW`
- Learning rate: `3e-4`
- Weight decay: `1e-4`
- Image size: `224`
- Epochs: `15`
- Label smoothing: `0.1`
- Early stopping patience: `5`
- Seed: `42`

## Dataset Setup

The Garbage V2 dataset is expected at:

```text
data/raw/garbage_v2
```

Check the dataset layout:

```bash
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

Create the training manifests:

```bash
python training/prepare_dataset.py --variant standardized_256 --seed 42
```

This writes:

- `datasets/manifests/four_class/standardized_256/train.csv`
- `datasets/manifests/four_class/standardized_256/val.csv`
- `datasets/manifests/four_class/standardized_256/test.csv`
- `datasets/manifests/four_class/standardized_256/summary.json`

## Windows GPU Training

One-time setup from the repo root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\training\windows\setup_windows_gpu.ps1 -PythonLauncher python3.13.exe
```

Train:

```powershell
.\training\windows\train_baseline.ps1
```

Environment check:

```powershell
.\.venv-win\Scripts\python.exe .\training\verify_environment.py --expect-device cuda
```

## Mac Training

One-time setup:

```bash
bash training/mac/setup_mac_training.sh
```

Train:

```bash
bash training/mac/train_baseline.sh
```

The Mac script uses `mps` when available and otherwise falls back to `cpu`.

Useful overrides:

```bash
DEVICE=mps BATCH_SIZE=32 EPOCHS=15 bash training/mac/train_baseline.sh
DEVICE=cpu BATCH_SIZE=16 WORKERS=2 bash training/mac/train_baseline.sh
```

## Manual Training Command

```bash
python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/standardized_256/train.csv \
  --val-manifest datasets/manifests/four_class/standardized_256/val.csv \
  --test-manifest datasets/manifests/four_class/standardized_256/test.csv \
  --model mobilenet_v3_large \
  --epochs 15 \
  --batch-size 32 \
  --workers 4 \
  --device cpu \
  --seed 42
```

Use `--device cuda` on the Windows GPU machine or `--device mps` on a supported Mac.

## Training Outputs

Each run writes a timestamped folder under `training/runs/`, for example:

```text
training/runs/20260402_194500_mobilenet_v3_large/
```

Important files:

- `config.json`
- `history.csv`
- `summary.json`
- `best.pt`
- `last.pt`
- `test_metrics.json`
- `test_confusion_matrix.json`

Copy the selected checkpoint to the deployed model path:

```text
models/best.pt
```

## Fine-Tuning From Pi Captures

The Pi runtime stores real captures and prediction records:

- `runtime/captures/`
- `runtime/inference_records/predictions.csv`
- `runtime/inference_records/json/`

To create feedback data:

1. Open `runtime/inference_records/predictions.csv`.
2. Fill in `confirmed_label` for reviewed captures.
3. Keep labels within `plastic`, `paper_cardboard`, `metal_glass`, and `trash_other`.
4. Add notes for lighting, occlusion, framing, or unusual objects when helpful.
5. Build feedback manifests:

```bash
python training/prepare_runtime_feedback.py
```

Fine-tune from the deployed checkpoint:

```bash
python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/runtime_feedback/train.csv \
  --val-manifest datasets/manifests/four_class/runtime_feedback/val.csv \
  --test-manifest datasets/manifests/four_class/runtime_feedback/test.csv \
  --model mobilenet_v3_large \
  --epochs 8 \
  --batch-size 32 \
  --device cpu \
  --init-checkpoint models/best.pt \
  --run-name runtime_feedback_finetune
```

Deploy the updated `best.pt` back to `models/best.pt` on the Pi.

## Optional BU SCC Runs

The SCC scripts are included for repeatable larger runs, but they are not required for the final prototype demo.

Setup:

```bash
bash training/scc/setup_scc_env.sh /projectnb/<project> /projectnb/<project>/TrashformerPro python3/3.10.12
```

Submit:

```bash
qsub training/scc/train_baseline.qsub
```

Edit project-specific paths in `training/scc/train_baseline.qsub` before submitting.

## Experiment Notes To Record

- Git commit hash
- machine and GPU type
- dataset variant
- class mapping
- split ratios and seed
- model name
- image size
- optimizer and learning rate
- batch size and epochs
- validation accuracy
- test accuracy
- macro F1
- confusion matrix
- real Pi failure cases