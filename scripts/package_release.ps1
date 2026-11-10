Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
python "$PSScriptRoot\package_release.py" windows
if ($LASTEXITCODE -ne 0) { throw "Release packaging failed" }
