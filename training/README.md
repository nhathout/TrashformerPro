# Training Workflow

## Recommendation

Train on the Windows 4080 PC first.

That is the fastest path to a usable baseline because:

- you control the environment
- you can debug failures quickly
- a single 4080 is more than enough for the first transfer-learning run

Use BU SCC after the baseline works locally and you want cleaner report runs, seed sweeps, or model comparisons.

Do not train on the Raspberry Pi. Use the Pi only for image capture and inference.

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

## Repo Files You Will Use

- `training/windows/setup_windows_gpu.ps1`
- `training/windows/train_baseline.ps1`
- `training/scc/setup_scc_env.sh`
- `training/scc/run_baseline.sh`
- `training/scc/train_baseline.qsub`
- `training/verify_environment.py`
- `training/prepare_dataset.py`
- `training/train_classifier.py`

## Shared Prerequisites

Before training on either machine:

1. Make sure the repo exists on that machine.
2. Make sure Garbage V2 exists at `data/raw/garbage_v2`.
3. Use only one dataset variant for training. This repo defaults to `standardized_256`.
4. Keep your large files in an appropriate location.
   On SCC, use `/projectnb/...`, not your home directory.

You can confirm the dataset layout with:

```bash
python scripts/inspect_garbage_dataset.py --variant standardized_256
```

## Windows 4080 PC

### One-Time Setup

1. Install:
   - Git
   - Python 3.10 to 3.13
   - the latest NVIDIA driver for the 4080

2. Put the repo in a simple local path such as:

```powershell
C:\dev\TrashformerPro
```

3. Open PowerShell in the repo root and run:

```powershell
.\training\windows\setup_windows_gpu.ps1
```

What this does:

- creates `.venv-win`
- installs `torch==2.6.0` and `torchvision==0.21.0` from the official PyTorch CUDA 12.6 wheel index
- installs the repo’s remaining Python dependency from `training/requirements.txt`
- verifies that CUDA is visible to PyTorch

If PowerShell script execution is blocked, run this in that shell first:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Verify The Environment

You can rerun the verification anytime:

```powershell
.\.venv-win\Scripts\python.exe .\training\verify_environment.py --expect-device cuda
```

You want to see:

- `cuda_available: True`
- a detected NVIDIA GPU
- a selected device of `cuda`

### Run The First Baseline

From the repo root:

```powershell
.\training\windows\train_baseline.ps1
```

That script:

1. verifies the CUDA environment
2. regenerates the dataset manifests with seed `42`
3. trains the baseline model on `standardized_256`

### If You Want The Manual Command

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

### Expected Outputs

Each run writes a new folder under `training/runs/`, for example:

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

### What To Do After The Windows Run

1. Look at validation/test accuracy and macro F1.
2. Inspect the confusion matrix.
3. Copy `best.pt` to the Raspberry Pi.
4. Run `inference/pi/classify_image.py` on real Pi captures.
5. If the baseline is decent, move to SCC for comparison runs.

## BU SCC

### Why SCC Comes Second

Use SCC once:

- the baseline command already works on the 4080 PC
- you want report-quality reruns
- you want to compare `mobilenet_v3_large`, `mobilenet_v3_small`, and `efficientnet_b0`
- you want multiple seeds or longer sweeps

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
- installs `torch==2.6.0` and `torchvision==0.21.0` from the official PyTorch CUDA 12.6 wheel index
- installs the repo’s remaining dependency
- verifies that the environment imports correctly

Note:

- the login node usually does not have a GPU attached, so setup only checks imports there
- the actual CUDA check happens inside the GPU batch job

### Configure The Batch Script

Edit `training/scc/train_baseline.qsub` and set:

- `PROJECT_ROOT`
- `VENV_PATH`
- optionally `PYTHON_MODULE`

The defaults are placeholders. Do not submit until those paths are correct for your SCC account.

### Submit The First SCC Run

From the repo root on SCC:

```bash
qsub training/scc/train_baseline.qsub
```

That batch script calls `training/scc/run_baseline.sh`, which:

1. loads the Python module
2. activates the SCC virtual environment
3. verifies CUDA from inside the GPU job
4. regenerates the manifests
5. trains the baseline model

### Track The Job

Useful SCC commands:

```bash
qstat -u $USER
qacct -j <job_id>
```

### If You Want A Manual SCC Run Instead Of `qsub`

First request an interactive GPU shell if needed, then:

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

Use `128` batch size on SCC only if it fits the GPU you requested. If not, reduce it to `64`.

## Exact Order I Recommend Right Now

1. Put the repo and dataset on the Windows 4080 PC.
2. Run `training/windows/setup_windows_gpu.ps1`.
3. Run `training/windows/train_baseline.ps1`.
4. Review the outputs in `training/runs/...`.
5. Copy `best.pt` to the Raspberry Pi and test real captures.
6. Only after that, set up SCC with `training/scc/setup_scc_env.sh`.
7. Submit the same baseline on SCC with `qsub training/scc/train_baseline.qsub`.
8. After the baseline is stable, run comparison experiments on SCC.

## Suggested SCC Follow-Up Experiments

Once the baseline works:

1. `mobilenet_v3_small` for faster Pi inference.
2. `efficientnet_b0` for an accuracy comparison.
3. three seeds: `42`, `52`, `62`.
4. longer training only if validation accuracy is still improving late.
5. fine-tuning on your own clear-plate images.

## Final Report Checklist

Record these for every experiment you may cite:

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
- real Pi-image failure cases

`training/train_classifier.py` now records machine, framework, device, and Git metadata in each run’s `config.json`.
