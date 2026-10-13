<#
.SYNOPSIS
  One-command Beatex setup on Windows: the model environment + the app environment.

.DESCRIPTION
  Clones Mapperatorinator into external/, builds its Python 3.10 venv with a
  CUDA build of PyTorch that matches your GPU driver, installs the model deps,
  then builds the Beatex app venv. Every step is skipped when it's already done,
  so it's safe to re-run. Needs git, uv and ffmpeg on PATH.

      powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.PARAMETER Cuda
  PyTorch wheel flavour: auto (default; picks from your NVIDIA driver), cu130, cu128, cu126 or cpu.

.PARAMETER DryRun
  Print what would run without changing anything.
#>
param(
  [ValidateSet('auto', 'cu130', 'cu128', 'cu126', 'cpu')][string]$Cuda = 'auto',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$ModelDir = Join-Path $Root 'external\Mapperatorinator'
$ModelPy = Join-Path $ModelDir '.venv\Scripts\python.exe'
$AppPy = Join-Path $Root '.venv\Scripts\python.exe'

function Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok([string]$msg) { Write-Host "    $msg" -ForegroundColor Green }
function Warn([string]$msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Run([string]$exe, [string[]]$argv) {
  Write-Host "    > $exe $($argv -join ' ')" -ForegroundColor DarkGray
  if ($DryRun) { return }
  & $exe @argv
  if ($LASTEXITCODE -ne 0) { throw "'$exe' failed with exit code $LASTEXITCODE" }
}

function Test-Import([string]$py, [string]$modules) {
  if (-not (Test-Path $py)) { return $false }
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $py -c "import $modules" *> $null; return ($LASTEXITCODE -eq 0) }
  finally { $ErrorActionPreference = $old }
}

function Get-CudaFlavour {
  if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Warn 'No NVIDIA GPU found: installing CPU PyTorch (generation works, but slowly).'
    return 'cpu'
  }
  $line = & nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | Select-Object -First 1
  $parts = $line -split ',\s*'
  $driver = [int](($parts[1] -split '\.')[0])
  Ok "GPU: $($parts[0]) (driver $($parts[1]))"
  if ($driver -ge 580) { return 'cu130' }
  Warn 'Driver is older than 580, so using CUDA 12.8 wheels (update the driver to use CUDA 13).'
  return 'cu128'
}

if ($DryRun) { Warn 'Dry run: nothing will be changed.' }

Step 'Checking prerequisites'
$missing = @()
foreach ($tool in @(@('git', 'winget install Git.Git'), @('uv', 'winget install astral-sh.uv'), @('ffmpeg', 'winget install Gyan.FFmpeg'))) {
  if (Get-Command $tool[0] -ErrorAction SilentlyContinue) { Ok "$($tool[0]) found" }
  else { $missing += "      $($tool[0])   ->   $($tool[1])" }
}
if ($missing.Count -gt 0) {
  Warn "Missing tools. Install them, open a new terminal, and run this again:`n$($missing -join "`n")"
  exit 1
}

Step 'Model code: Mapperatorinator (external/)'
if (Test-Path (Join-Path $ModelDir 'inference.py')) { Ok 'already cloned' }
else { Run 'git' @('clone', '--recurse-submodules', 'https://github.com/OliBomby/Mapperatorinator.git', $ModelDir) }

Step 'Model environment: Python 3.10 venv'
if (Test-Path $ModelPy) { Ok 'venv exists' }
else { Run 'uv' @('venv', (Join-Path $ModelDir '.venv'), '--python', '3.10') }

Step 'PyTorch'
if (Test-Import $ModelPy 'torch, torchaudio') {
  $info = & $ModelPy -c "import torch; print(torch.__version__, '| CUDA available:', torch.cuda.is_available())"
  Ok "already installed: $info"
} else {
  if ($Cuda -eq 'auto') { $Cuda = Get-CudaFlavour }
  Run 'uv' @('pip', 'install', '--python', $ModelPy, 'torch', 'torchaudio', '--index-url', "https://download.pytorch.org/whl/$Cuda")
}

Step 'Model dependencies'
if (Test-Import $ModelPy 'hydra, transformers, slider, nnAudio') { Ok 'already installed' }
else { Run 'uv' @('pip', 'install', '--python', $ModelPy, '-r', (Join-Path $Root 'setup\mapperatorinator-requirements-win.txt')) }

Step 'App environment: Python 3.12 venv + Beatex'
if (Test-Path $AppPy) { Ok 'venv exists' }
else { Run 'uv' @('venv', (Join-Path $Root '.venv'), '--python', '3.12') }
if (Test-Import $AppPy 'beatex, numpy, pydub') { Ok 'Beatex + extras installed' }
else { Run 'uv' @('pip', 'install', '--python', $AppPy, '-e', "$Root[app]") }

Step 'Done'
Ok 'Double-click Beatex.bat to open Beatex Studio.'
Ok 'The first generation downloads the model weights from Hugging Face (one time).'
Ok 'No song handy? python tools\demo_track.py makes a royalty-free one in data\demo\.'
