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

- `training/mac/setup_mac_training.sh`
- `training/mac/train_baseline.sh`
- `training/windows/setup_windows_gpu.ps1`
- `training/windows/train_baseline.ps1`
- `training/prepare_dataset.py`
- `training/prepare_runtime_feedback.py`
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

## Mac

Use the Mac path when you want a local baseline before moving to the Pi, or when you want to iterate without the Windows GPU machine.

The Mac scripts work on:

- Apple Silicon Macs with `mps`
- Intel Macs with `cpu`

### One-Time Setup

From the repo root:

```bash
bash training/mac/setup_mac_training.sh
```

If you need a specific Python binary:

```bash
PYTHON_BIN=python3.13 bash training/mac/setup_mac_training.sh
```

What the setup script does:

- creates `.venv-mac`
- installs `torch==2.6.0` and `torchvision==0.21.0`
- installs `training/requirements.txt`
- runs the environment check

### Train The Baseline

From the repo root:

```bash
bash training/mac/train_baseline.sh
```

The script auto-selects the device:

- `mps` when available
- otherwise `cpu`

Useful overrides:

```bash
DEVICE=mps BATCH_SIZE=32 EPOCHS=15 bash training/mac/train_baseline.sh
DEVICE=cpu BATCH_SIZE=16 WORKERS=2 bash training/mac/train_baseline.sh
```

### Manual Mac Training Command

```bash
source .venv-mac/bin/activate
python training/prepare_dataset.py --variant standardized_256 --seed 42

python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/standardized_256/train.csv \
  --val-manifest datasets/manifests/four_class/standardized_256/val.csv \
  --test-manifest datasets/manifests/four_class/standardized_256/test.csv \
  --model mobilenet_v3_large \
  --epochs 15 \
  --batch-size 32 \
  --workers 4 \
  --device mps \
  --seed 42
```

If your Mac does not support `mps`, switch `--device` to `cpu`.

## What To Do After Training

After the first baseline works, the recommended next step is Pi validation, not more experiments.

1. Copy `best.pt` to the Raspberry Pi, usually as `models/best.pt`.
2. Run inference on real plate captures.
3. Capture an empty reference image with `/usr/bin/python3 scripts/pi/capture_empty_reference.py`.
4. Run the full Pi loop with `/usr/bin/python3 scripts/pi/full_system_runner.py --checkpoint models/best.pt --classifier-python .venv/bin/python --stable-hold-seconds 2.0`.
5. Review the failure cases from the real hardware setup.
6. Fine-tune later on those real captures if needed.

See `inference/README.md` for the Pi-side workflow.

## Fine-Tune On Confirmed Pi Captures

The Pi runtime workflow already archives:

- the latest live frame plus locked classification captures in `runtime/captures/`
- every logged prediction record in `runtime/inference_records/predictions.csv`

That same feedback loop now also applies to locked classifications from the app `Live Monitor` tab when it is running on the Pi.

To turn those into a fine-tuning set:

1. Open `runtime/inference_records/predictions.csv`.
2. Fill in `confirmed_label` for the captures you want to train on.
3. Keep labels inside the four deployed classes:
   `plastic`, `paper_cardboard`, `metal_glass`, `trash_other`.
4. Optionally add notes for lighting, occlusion, or staging issues.
5. Build combined manifests:

```bash
python training/prepare_runtime_feedback.py
```

That writes:

- `datasets/manifests/four_class/runtime_feedback/feedback_all.csv`
- `datasets/manifests/four_class/runtime_feedback/train.csv`
- `datasets/manifests/four_class/runtime_feedback/val.csv`
- `datasets/manifests/four_class/runtime_feedback/test.csv`
- `datasets/manifests/four_class/runtime_feedback/summary.json`

The combined `train.csv`, `val.csv`, and `test.csv` keep the original baseline dataset and append the confirmed Pi captures on top.

### Fine-Tune From The Current `best.pt`

Use `--init-checkpoint` to keep training from the deployed classifier instead of starting over from ImageNet weights.

Example on Mac or Linux:

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

Example on the Windows GPU machine:

```powershell
.\.venv-win\Scripts\python.exe .\training\train_classifier.py `
  --train-manifest datasets\manifests\four_class\runtime_feedback\train.csv `
  --val-manifest datasets\manifests\four_class\runtime_feedback\val.csv `
  --test-manifest datasets\manifests\four_class\runtime_feedback\test.csv `
  --model mobilenet_v3_large `
  --epochs 8 `
  --batch-size 64 `
  --device cuda `
  --init-checkpoint models\best.pt `
  --run-name runtime_feedback_finetune
```

The fine-tuning run writes a new `training/runs/<run_name>/best.pt`. Deploy that checkpoint back to the Pi when you are ready to test the updated model.

## Pull Pi Captures To Mac, Label Them, Fine-Tune, And Redeploy

This is the most practical improvement loop before a presentation.

### 1. Copy The Current Pi Data To Your Mac

Run this on your Mac from the repo root:

```bash
scp <pi-user>@<pi-ip>:~/TrashformerPro/models/best.pt models/best.pt

mkdir -p runtime/captures runtime/inference_records runtime/inference_records/json

rsync -av <pi-user>@<pi-ip>:~/TrashformerPro/runtime/captures/ runtime/captures/
rsync -av <pi-user>@<pi-ip>:~/TrashformerPro/runtime/inference_records/ runtime/inference_records/
```

That gives you:

- the current deployed checkpoint
- all saved captures from the Pi
- the prediction log you will relabel

### 2. Label The Mistakes On Your Mac

Open:

```text
runtime/inference_records/predictions.csv
```

Fill in:

- `confirmed_label` with the true class
- `notes` if you want to track glare, overlap, bad framing, or unusual objects

Valid labels remain:

- `plastic`
- `paper_cardboard`
- `metal_glass`
- `trash_other`

### 3. Build The Feedback Manifests On Your Mac

Set up the Mac training environment if needed:

```bash
bash training/mac/setup_mac_training.sh
source .venv-mac/bin/activate
```

Prepare the baseline manifests and the feedback manifests:

```bash
python training/prepare_dataset.py --variant standardized_256 --seed 42
python training/prepare_runtime_feedback.py
```

### 4. Fine-Tune From The Current Pi Checkpoint On Your Mac

For Apple Silicon Macs:

```bash
python training/train_classifier.py \
  --train-manifest datasets/manifests/four_class/runtime_feedback/train.csv \
  --val-manifest datasets/manifests/four_class/runtime_feedback/val.csv \
  --test-manifest datasets/manifests/four_class/runtime_feedback/test.csv \
  --model mobilenet_v3_large \
  --epochs 8 \
  --batch-size 32 \
  --workers 4 \
  --device mps \
  --init-checkpoint models/best.pt \
  --run-name runtime_feedback_finetune
```

If your Mac does not support `mps`, change `--device mps` to `--device cpu`.

### 5. Deploy The Updated Checkpoint Back To The Pi

Run this on your Mac:

```bash
scp training/runs/runtime_feedback_finetune/best.pt \
  <pi-user>@<pi-ip>:~/TrashformerPro/models/best.pt
```

Then on the Pi, restart whichever runtime you are using:

- the app backend in `apps/trashformer_app/README.md`
- or the hardware loop in `scripts/pi/README.md`

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
