# Build standalone Windows x86_64 executables for recharge-ai-task.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ([Environment]::Is64BitOperatingSystem -ne $true) {
    Write-Error "Release builds target x86_64 Windows only."
}

New-Item -ItemType Directory -Force (Join-Path $Root "build") | Out-Null
python "$PSScriptRoot\windows_version.py" "$Root\build\windows-version.txt"
if ($LASTEXITCODE -ne 0) { throw "Version resource generation failed" }
$Locales = Join-Path $Root "recharge_ai_task\locales"
$CommonArgs = @(
    "--noconfirm", "--onefile",
    "--version-file", (Join-Path $Root "build\windows-version.txt"),
    "--specpath", (Join-Path $Root "build"),
    "--paths", $Root,
    "--collect-data", "recharge_ai_task",
    "--icon", (Join-Path $Root "recharge_ai_task\assets\recharge-ai-task.ico"),
    "--add-data", "$Locales;recharge_ai_task\locales"
)

Write-Host "Building recharge-ai-task CLI..."
pyinstaller @CommonArgs --console `
  --name recharge-ai-task-cli `
  --collect-all winpty `
  scripts/entry_cli.py
if ($LASTEXITCODE -ne 0) { throw "CLI build failed" }

Write-Host "Building the recharge-ai-task Windows tray..."
pyinstaller @CommonArgs --windowed `
  --name recharge-ai-task `
  --collect-all winpty `
  --collect-all pystray `
  scripts/entry_windows.py
if ($LASTEXITCODE -ne 0) { throw "Desktop build failed" }

# Windows retains a console companion; no legacy GUI/tray aliases are shipped.
foreach ($Name in @("recharge-ai-task-tray.exe", "recharge-ai-task-gui.exe", "recharge-ai-task-tray.cmd", "recharge-ai-task-gui.cmd")) {
    $Old = Join-Path $Root "dist\$Name"
    if (Test-Path $Old) { Remove-Item $Old -Force }
}
& "$Root\dist\recharge-ai-task-cli.exe" --help
if ($LASTEXITCODE -ne 0) { throw "Packaged CLI help failed" }
& "$Root\dist\recharge-ai-task-cli.exe" run --help
if ($LASTEXITCODE -ne 0) { throw "Packaged CLI run help failed" }
Write-Host "Output: dist\recharge-ai-task.exe and dist\recharge-ai-task-cli.exe"
