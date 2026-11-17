$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv-local-models/Scripts/python.exe'
Push-Location $repoRoot
try {
    & $pythonExe -m local_model_testing.launch stop
    if ($LASTEXITCODE -ne 0) { throw 'Ownership verification/stop failed; record retained.' }
} finally { Pop-Location }
