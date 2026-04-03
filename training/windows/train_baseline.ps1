param(
    [string]$VenvPath = ".venv-win",
    [string]$Variant = "standardized_256",
    [int]$Seed = 42,
    [string]$Model = "mobilenet_v3_large",
    [int]$Epochs = 15,
    [int]$BatchSize = 64,
    [int]$Workers = 8,
    [string]$Device = "cuda",
    [string]$RunName = ""
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot "$VenvPath\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe. Run training\windows\setup_windows_gpu.ps1 first."
}

Invoke-CheckedCommand $pythonExe @("training\verify_environment.py", "--expect-device", "cuda")
Invoke-CheckedCommand $pythonExe @("training\prepare_dataset.py", "--variant", $Variant, "--seed", $Seed)

$trainArgs = @(
    "training\train_classifier.py",
    "--train-manifest", "datasets\manifests\four_class\$Variant\train.csv",
    "--val-manifest", "datasets\manifests\four_class\$Variant\val.csv",
    "--test-manifest", "datasets\manifests\four_class\$Variant\test.csv",
    "--model", $Model,
    "--epochs", $Epochs,
    "--batch-size", $BatchSize,
    "--workers", $Workers,
    "--device", $Device,
    "--seed", $Seed
)

if ($RunName -ne "") {
    $trainArgs += @("--run-name", $RunName)
}

Invoke-CheckedCommand $pythonExe $trainArgs
