param(
    [switch]$TcpOnly,
    [ValidateRange(1,300)][int]$TimeoutSeconds = 15,
    [string]$Python
)

$script:MedResidentRepoRoot = Split-Path -Parent $PSScriptRoot

function Test-MedResidentLLM {
    param(
        [switch]$TcpOnly,
        [ValidateRange(1,300)][int]$TimeoutSeconds = 15,
        [string]$Python
    )
    if (-not $Python) {
        $localPython = Join-Path $script:MedResidentRepoRoot '.venv-extraction/Scripts/python.exe'
        $existingPython = Join-Path $env:TEMP 'medresident-extraction-venv/Scripts/python.exe'
        if (Test-Path -LiteralPath $localPython) { $Python = $localPython }
        elseif (Test-Path -LiteralPath $existingPython) { $Python = $existingPython }
        else { $Python = 'python' }
    }
    Push-Location -LiteralPath $script:MedResidentRepoRoot
    try {
        $probeArgs = @('-m', 'knowledge_pipeline.connection', '--timeout', "$TimeoutSeconds")
        if ($TcpOnly) { $probeArgs += '--tcp-only' }
        & $Python @probeArgs
    }
    finally { Pop-Location }
}

if ($MyInvocation.InvocationName -ne '.') {
    Test-MedResidentLLM -TcpOnly:$TcpOnly -TimeoutSeconds $TimeoutSeconds -Python $Python
    exit $LASTEXITCODE
}
