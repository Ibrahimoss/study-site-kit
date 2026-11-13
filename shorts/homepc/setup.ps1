# Sets up a "voice PC": Kokoro (text to speech) and Whisper (optional double check) in one folder.
# Python, packages, the voice model and caches all live inside that folder; nothing else on the PC changes.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1                 # folder: <your home folder>\study-kit-tts
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Dir E:\voices  # another folder (no spaces in the path)
#
# Then put the folder in course.json: "voicePC": {"host": "...", "key": "...", "dir": "<the folder>"}
# (leave "dir" out when you used the default folder). See README.md next to this file.
param(
  [string]$Dir = (Join-Path $HOME "study-kit-tts"),
  [switch]$NoWhisper
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ($Dir -match "\s") { throw "Pick a folder without spaces in its path: $Dir" }
New-Item -ItemType Directory -Force $Dir | Out-Null
Set-Location $Dir
New-Item -ItemType Directory -Force "$Dir\out" | Out-Null
$env:UV_PYTHON_INSTALL_DIR = "$Dir\python"
$env:UV_CACHE_DIR = "$Dir\uv-cache"
$env:HF_HOME = "$Dir\hf"

if (-not (Test-Path "$Dir\uv\uv.exe")) {
  Write-Output "downloading uv (a small Python installer)"
  Invoke-WebRequest -UseBasicParsing "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile "$Dir\uv.zip"
  Expand-Archive "$Dir\uv.zip" -DestinationPath "$Dir\uv" -Force
  Remove-Item "$Dir\uv.zip"
}
$uv = Get-ChildItem -Recurse -Filter uv.exe "$Dir\uv" | Select-Object -First 1 -ExpandProperty FullName
& $uv --version

if (-not (Test-Path "$Dir\venv\Scripts\python.exe")) {
  Write-Output "creating a Python 3.12 environment"
  & $uv venv --python 3.12 --seed "$Dir\venv"
}
$py = "$Dir\venv\Scripts\python.exe"

$gpu = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($gpu) {
  Write-Output "installing PyTorch for the NVIDIA graphics card (large download)"
  & $uv pip install --python $py torch --index-url https://download.pytorch.org/whl/cu126
} else {
  Write-Output "no NVIDIA graphics card found: installing PyTorch for the processor (slower narration)"
  & $uv pip install --python $py torch --index-url https://download.pytorch.org/whl/cpu
}
Write-Output "installing Kokoro"
& $uv pip install --python $py kokoro soundfile numpy
if (-not $NoWhisper) {
  Write-Output "installing Whisper (double-checks the narration; optional)"
  & $uv pip install --python $py openai-whisper
}

& $py -c "import torch; print('torch', torch.__version__, 'gpu', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
Write-Output "SETUP DONE in $Dir"
