param([switch]$Smoke)
& (Join-Path $PSScriptRoot 'Start-LocalModel.ps1') -Kind teaching -Smoke:$Smoke
