<#
.SYNOPSIS
  Windows helper: Hailo ONNX->HEF compile via WSL2 (docs / SIMULATED path).

.DESCRIPTION
  Status: SIMULATED — does NOT claim HARDWARE validation.
  Hailo Dataflow Compiler is x86_64 Linux only. Real work: scripts/hailo_compile.sh

.PARAMETER Arch
  hailo8l | hailo8 | hailo10h (default hailo8l for AI HAT+ 13 TOPS)

.PARAMETER DryRun
  Print commands only; do not invoke WSL.
#>
param(
    [ValidateSet("hailo8l", "hailo8", "hailo10h")]
    [string]$Arch = "hailo8l",
    [switch]$DryRun,
    [string]$Model = "models/weed_crop_yolox_s.onnx",
    [string]$Calib = "data/weed-crop-aerial/train/images"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "Agri-Edge Hailo compile (SIMULATED on Windows — real DFC runs in WSL2)"
Write-Host "  arch=$Arch model=$Model"
Write-Host "  STATUS: NOT HARDWARE-validated. See docs/architecture/hailo-compile.md"

$unixRepo = ((Get-Location).Path -replace '\\', '/')
if ($unixRepo -match '^[A-Za-z]:') {
    $drive = $unixRepo.Substring(0, 1).ToLower()
    $unixRepo = "/mnt/$drive" + $unixRepo.Substring(2)
}
$wslInner = "cd '$unixRepo' && bash scripts/hailo_compile.sh --arch $Arch --model $Model --calib $Calib"
Write-Host "  WSL: wsl -e bash -lc `"$wslInner`""

if ($DryRun) {
    Write-Host "Dry-run only. Exiting."
    exit 0
}

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    Write-Error "WSL not found. Install Ubuntu-22.04 WSL2 + Hailo DFC. See docs/architecture/hailo-compile.md"
    exit 1
}

wsl -e bash -lc $wslInner
exit $LASTEXITCODE
