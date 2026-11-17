param(
    [Parameter(Mandatory=$true)][ValidateSet('medical','teaching')][string]$Kind,
    [switch]$Smoke
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv-local-models/Scripts/python.exe'
$workerArgs = @('-m','local_model_testing.launch',$Kind)
if ($Smoke) { $workerArgs += '--smoke' }
Push-Location $repoRoot
try {
    & $pythonExe @workerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Local model test stopped; see terminal error and data/local-model-tests.' }
} finally { Pop-Location }
