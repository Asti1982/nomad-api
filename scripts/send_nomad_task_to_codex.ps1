param(
  [int]$DelaySeconds = 3,
  [switch]$CopyOnly,
  [switch]$NoEnter,
  [switch]$Preview
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
  throw "Python was not found in PATH."
}

$prompt = (& $python.Source main.py --cli codex-task | Out-String).Trim()
if (-not $prompt) {
  throw "Nomad did not produce a Codex task prompt."
}

Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Clipboard]::SetText($prompt)

if ($Preview) {
  Write-Output $prompt
}

Write-Output "copied_to_clipboard=true"

if ($CopyOnly) {
  exit 0
}

Write-Output "focus_codex_box_within_seconds=$DelaySeconds"
Start-Sleep -Seconds $DelaySeconds
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 250
if (-not $NoEnter) {
  [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
  Write-Output "enter_pressed=true"
} else {
  Write-Output "enter_pressed=false"
}
