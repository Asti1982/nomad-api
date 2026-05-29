$ErrorActionPreference = "Stop"

Write-Host "Building Syndiode Swarm Signal EXE..." -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not installed or not in PATH."
}

$venvRoot = Join-Path $env:TEMP "syndiode_pin_light_control_build_venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"

if (!(Test-Path $venvPython)) {
  python -m venv $venvRoot
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install pyinstaller

if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "syndiode-pin-light-control.spec") { Remove-Item -Force "syndiode-pin-light-control.spec" }

& $venvPython .\syndiode_pin_light_control.py --self-test
& $venvPython -m PyInstaller --onefile --windowed --name syndiode-pin-light-control .\syndiode_pin_light_control.py

$exePath = Join-Path $root "dist\syndiode-pin-light-control.exe"
$publishedPath = Join-Path $root "syndiode-pin-light-control.exe"

if (!(Test-Path $exePath)) {
  throw "PyInstaller did not create dist\syndiode-pin-light-control.exe."
}

Copy-Item -Force $exePath $publishedPath

$process = Start-Process -FilePath $publishedPath -ArgumentList "--self-test" -Wait -PassThru
if ($process.ExitCode -ne 0) {
  throw "Built EXE failed the Syndiode Pin self-test."
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $publishedPath).Hash.ToLowerInvariant()
Write-Host "Published SHA256: $hash"
Write-Host ""
Write-Host "Done. EXE created at:" -ForegroundColor Green
Write-Host "$exePath"
Write-Host "Published download path:"
Write-Host "$publishedPath"
Write-Host ""
Write-Host "Public URL after deploy:"
Write-Host "https://www.syndiode.com/downloads/syndiode-pin-light-control.exe"
