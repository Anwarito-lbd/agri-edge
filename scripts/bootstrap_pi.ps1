#Requires -Version 5.1
<#
.SYNOPSIS
  Copy agri-edge core to the Pi and run pi_setup.sh + camera checks.
#>
param(
  [string]$HostName = "raspberrypi.local",
  [string]$User = "pi",
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) {
  $RepoRoot = Join-Path $env:USERPROFILE "OneDrive\Desktop\agricultrul"
}
$sshTarget = "${User}@${HostName}"
$remoteDir = "~/agri-edge"

Write-Host "== agri-edge Pi bootstrap =="
Write-Host "Local:  $RepoRoot"
Write-Host "Remote: ${sshTarget}:$remoteDir"

# Ensure remote dir
ssh $sshTarget "mkdir -p $remoteDir"

# Prefer scp/rsync of needed trees only (skip huge vendor/weights if present)
$exclude = @('vendor', 'weights', 'YOLOX_outputs', 'YOLOX_outputs_crashed', '.venv', 'data', 'runs', 'workstation', '.pytest_cache', 'node_modules')
$staging = Join-Path $env:TEMP "agri-edge-pi-sync"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

Write-Host "Staging slim copy (excluding vendor/weights)..."
robocopy $RepoRoot $staging /E /XD $exclude /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
# robocopy exit codes 0-7 are success-ish
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

Write-Host "Uploading via scp (this can take a few minutes)..."
scp -r "$staging\*" "${sshTarget}:${remoteDir}/"
Remove-Item -Recurse -Force $staging

Write-Host "Running pi_setup.sh on the Pi (needs sudo on Pi)..."
ssh -t $sshTarget "cd $remoteDir && bash scripts/pi_setup.sh"

Write-Host "Camera + agri_edge smoke..."
ssh $sshTarget @"
cd $remoteDir
set -e
.venv/bin/python -c "import agri_edge, numpy, yaml; print('agri_edge OK', getattr(agri_edge,'__version__','?'))"
command -v rpicam-hello >/dev/null && rpicam-hello -t 2000 --nopreview || echo 'rpicam-hello missing'
.venv/bin/python - <<'PY'
from pathlib import Path
try:
    from picamera2 import Picamera2
except Exception as e:
    print('picamera2 import failed:', e)
    raise SystemExit(0)
import numpy as np
c = Picamera2()
c.configure(c.create_still_configuration())
c.start()
a = c.capture_array('main')
print('frame', a.shape, a.dtype)
# Heuristic: if pointed at red, channel 0 should dominate for RGB
means = a.reshape(-1, a.shape[-1]).mean(axis=0)
print('channel_means_RGB_or_BGR_order', means.tolist())
print('NOTE: point at a red object; if ch0 is NOT largest, frames are likely BGR')
c.stop()
PY
.venv/bin/python - <<'PY'
# Green-on-brown import smoke (no field required)
from agri_edge.inference.greenonbrown import GreenOnBrown
print('greenonbrown import OK', GreenOnBrown)
PY
"@

Write-Host ""
Write-Host "[ok] Bootstrap finished. Read channel_means note above."
Write-Host "Next: reflectance panel + field-edge annotate for validated_locally."
