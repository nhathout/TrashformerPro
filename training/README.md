# Training Workflow

This document is only about model training and dataset preparation.

If you want to run the trained model on the Raspberry Pi, use `inference/README.md` instead.

## Current Baseline

The first baseline in this repo is:

- task: 4-class image classification
- dataset variant: `standardized_256`
- mapping: `plastic`, `paper_cardboard`, `metal_glass`, `trash_other`
- model: `mobilenet_v3_large`
- initialization: ImageNet pretrained weights
- optimizer: `AdamW`
- learning rate: `3e-4`
- weight decay: `1e-4`
- image size: `224`
- epochs: `15`
- label smoothing: `0.1`
- early stopping patience: `5`
- seed: `42`

## Files You Will Use

- `training/windows/setup_windows_gpu.ps1`
- `training/windows/train_baseline.ps1`
- `training/prepare_dataset.py`
- `training/train_classifier.py`
- `training/verify_environment.py`
- `training/scc/setup_scc_env.sh`
- `training/scc/run_baseline.sh`
- `training/scc/train_baseline.qsub`

## Shared Prerequisites

Before training on any machine:

1. Make sure the repo exists on that machine.
2. Make sure Garbage V2 exists at `data/raw/garbage_v2`.
3. Use one dataset variant at a time. This repo defaults to `standardized_256`.
4. Keep large training artifacts in appropriate storage for that machine.

You can confirm the dataset layout with:

```bash
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

## Prepare The Dataset Manifests

From the repo root:

```bash
python training/prepare_dataset.py --variant standardized_256 --seed 42
```

This creates:

- `datasets/manifests/four_class/standardized_256/train.csv`
- `datasets/manifests/four_class/standardized_256/val.csv`
- `datasets/manifests/four_class/standardized_256/test.csv`
- `datasets/manifests/four_class/standardized_256/summary.json`

## Windows 4080 PC

### One-Time Setup

Install:

- Git
- Python 3.10 to 3.13
- the latest NVIDIA driver for the RTX 4080

Then, from the repo root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\training\windows\setup_windows_gpu.ps1 -PythonLauncher python3.13.exe
```

What the setup script does:

- creates `.venv-win`
- installs `torch==2.6.0` and `torchvision==0.21.0` from the CUDA 12.6 wheel index
- installs `training/requirements.txt`
- verifies that CUDA is visible to PyTorch

You can rerun the environment check any time with:

```powershell
.\.venv-win\Scripts\python.exe .\training\verify_environment.py --expect-device cuda
```

You want to see:

- `cuda_available: True`
- your NVIDIA GPU in the detected device list
- `selected_device: cuda`

### Train The Baseline

From the repo root:

```powershell
.\training\windows\train_baseline.ps1
```

That script:

1. verifies the CUDA environment
2. regenerates the manifests with seed `42`
3. trains the baseline model on `standardized_256`

### Manual Training Command

```powershell
.\.venv-win\Scripts\python.exe .\training\prepare_dataset.py --variant standardized_256 --seed 42

.\.venv-win\Scripts\python.exe .\training\train_classifier.py `
  --train-manifest datasets\manifests\four_class\standardized_256\train.csv `
  --val-manifest datasets\manifests\four_class\standardized_256\val.csv `
  --test-manifest datasets\manifests\four_class\standardized_256\test.csv `
  --model mobilenet_v3_large `
  --epochs 15 `
  --batch-size 64 `
  --workers 8 `
  --device cuda `
  --seed 42
```

### Training Outputs

Each run writes a timestamped folder under `training/runs/`, for example:

```text
training/runs/20260402_194500_mobilenet_v3_large/
```

Important artifacts:

- `config.json`
- `history.csv`
- `summary.json`
- `best.pt`
- `last.pt`
- `test_metrics.json`
- `test_confusion_matrix.json`

## What To Do After Training

After the first baseline works, the recommended next step is Pi validation, not more experiments.

1. Copy `best.pt` to the Raspberry Pi.
2. Run inference on real plate captures.
3. Review the failure cases from the real hardware setup.
4. Fine-tune later on those real captures if needed.

See `inference/README.md` for the Pi-side workflow.

## BU SCC

SCC is optional and comes second.

Use it when:

- the Windows baseline already works
- you want repeatable comparison runs
- you want multiple seeds or longer sweeps
- you need a cleaner environment for report-quality reruns

### One-Time SCC Setup

1. Put the repo in project space, for example:

```bash
/projectnb/<project>/TrashformerPro
```

2. SSH into SCC and check the available Python modules:

```bash
module avail python3
```

3. Create the virtual environment with the provided setup script:

```bash
bash training/scc/setup_scc_env.sh /projectnb/<project> /projectnb/<project>/TrashformerPro python3/3.10.12
```

What this does:

- loads the requested BU Python module
- creates `/projectnb/<project>/venvs/trashformerpro-cu126`
- installs `torch==2.6.0` and `torchvision==0.21.0`
- installs the remaining repo dependency
- verifies that the environment imports correctly

### Submit The SCC Baseline

Edit `training/scc/train_baseline.qsub` so its project-specific paths are correct, then submit:

```bash
qsub training/scc/train_baseline.qsub
```

Useful SCC commands:

```bash
qstat -u $USER
qacct -j <job_id>
```

### Manual SCC Training Command

```bash
module load python3/3.10.12
source /projectnb/<project>/venvs/trashformerpro-cu126/bin/activate

python training/verify_environment.py --expect-device cuda
python training/prepare_dataset.py --variant standardized_256 --seed 42
python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/standardized_256/train.csv \
  --val-manifest datasets/manifests/four_class/standardized_256/val.csv \
  --test-manifest datasets/manifests/four_class/standardized_256/test.csv \
  --model mobilenet_v3_large \
  --epochs 15 \
  --batch-size 128 \
  --workers 8 \
  --device cuda \
  --seed 42
```

Reduce the batch size if the requested SCC GPU cannot hold `128`.

## Training Metadata Checklist

Record these for any experiment you may want to keep or report:

- Git commit hash
- date and machine used
- GPU type
- dataset variant
- exact class mapping
- split ratios
- seed
- model name
- pretrained or not
- image size
- optimizer
- learning rate
- batch size
- weight decay
- epochs requested
- epochs completed
- early stopping behavior
- validation accuracy
- test accuracy
- macro F1
- confusion matrix
- real Pi failure cases from downstream validation
