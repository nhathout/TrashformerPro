param(
    [string]$VenvPath = ".venv-win",
    [string]$PythonLauncher = "py",
    [string]$TorchVersion = "2.6.0",
    [string]$TorchVisionVersion = "0.21.0",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu126"
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

Invoke-CheckedCommand $PythonLauncher @("-m", "venv", $VenvPath)

$pythonExe = Join-Path $repoRoot "$VenvPath\Scripts\python.exe"

Invoke-CheckedCommand $pythonExe @("-m", "pip", "install", "--upgrade", "pip")
Invoke-CheckedCommand $pythonExe @("-m", "pip", "install", "torch==$TorchVersion", "torchvision==$TorchVisionVersion", "--index-url", $TorchIndexUrl)
Invoke-CheckedCommand $pythonExe @("-m", "pip", "install", "-r", "training\requirements.txt")
Invoke-CheckedCommand $pythonExe @("training\verify_environment.py", "--expect-device", "cuda")

Write-Host ""
Write-Host "Windows GPU environment ready."
Write-Host "Activate with:"
Write-Host "  $VenvPath\Scripts\Activate.ps1"
