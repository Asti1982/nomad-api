$ErrorActionPreference = "Stop"

Write-Host "Building Nomad Transition Worker EXE..." -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not installed or not in PATH."
}

python -m pip install --upgrade pip
python -m pip install pyinstaller

if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "nomad_transition_worker.spec") { Remove-Item -Force "nomad_transition_worker.spec" }

python -m PyInstaller --onefile --name nomad_transition_worker nomad_transition_worker.py

$exePath = Join-Path $root "dist\nomad_transition_worker.exe"
$publishedPath = Join-Path $root "nomad_transition_worker.exe"
if (Test-Path $exePath) {
  Copy-Item -Force $exePath $publishedPath
}

Write-Host ""
Write-Host "Done. EXE created at:" -ForegroundColor Green
Write-Host "$exePath"
Write-Host "Published download path:"
Write-Host "$publishedPath"
Write-Host ""
Write-Host "Run with:"
Write-Host ".\dist\nomad_transition_worker.exe --base-url https://syndiode.com --loop --cycles 0"
