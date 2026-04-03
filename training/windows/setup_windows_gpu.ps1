param(
    [string]$VenvPath = ".venv-win",
    [string]$PythonLauncher = "py",
    [string]$TorchVersion = "2.6.0",
    [string]$TorchVisionVersion = "0.21.0",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu126"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $repoRoot

& $PythonLauncher -m venv $VenvPath

$pythonExe = Join-Path $repoRoot "$VenvPath\Scripts\python.exe"

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install "torch==$TorchVersion" "torchvision==$TorchVisionVersion" --index-url $TorchIndexUrl
& $pythonExe -m pip install -r "training\requirements.txt"
& $pythonExe "training\verify_environment.py" --expect-device cuda

Write-Host ""
Write-Host "Windows GPU environment ready."
Write-Host "Activate with:"
Write-Host "  $VenvPath\Scripts\Activate.ps1"
