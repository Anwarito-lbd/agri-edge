#Requires -Version 5.1
<#
.SYNOPSIS
  Discover agri-edge Pi on LAN and prepare SSH bootstrap.
.NOTES
  Run on the Windows laptop after the Pi is on Bookworm + network.
#>
param(
  [string]$HostName = "raspberrypi.local",
  [string]$User = "pi",
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) {
  $RepoRoot = Join-Path ([Environment]::GetFolderPath('Desktop')) "agricultrul"
  if (-not (Test-Path $RepoRoot)) {
    $RepoRoot = Join-Path $env:USERPROFILE "OneDrive\Desktop\agricultrul"
  }
}

Write-Host "== agri-edge Pi discover =="
Write-Host "Looking for $HostName ..."

function Test-PiHost([string]$h) {
  try {
    $r = Resolve-DnsName $h -ErrorAction Stop | Select-Object -First 1
    return $true
  } catch { return $false }
}

$found = $false
$ip = $null
if (Test-PiHost $HostName) {
  try {
    $ip = (Resolve-DnsName $HostName -Type A -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
  } catch {}
  $found = $true
  Write-Host "[ok] DNS resolves $HostName -> $ip"
} else {
  Write-Host "[!!] $HostName not resolving yet. Scanning common mDNS / ARP hints..."
  arp -a | Select-String -Pattern "dynamic" | ForEach-Object { $_.Line }
}

# SSH probe (BatchMode so we don't hang on password if key missing)
Write-Host ""
Write-Host "SSH probe (may ask for password if no key yet):"
$sshTarget = "${User}@${HostName}"
$probe = "uname -a; tr -d '\0' </proc/device-tree/model 2>/dev/null; getconf LONG_BIT; cat /etc/os-release | head -5"
ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new $sshTarget $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "[!!] SSH failed. Fix: enable SSH in Imager, same Wi-Fi as laptop, or use Ethernet."
  Write-Host "    Then re-run: powershell -File scripts\discover_pi.ps1"
  exit 1
}

Write-Host ""
Write-Host "[ok] Pi reachable as $sshTarget"
Write-Host "Next: powershell -File scripts\bootstrap_pi.ps1 -User $User -HostName $HostName"
