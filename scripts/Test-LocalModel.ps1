param([Parameter(Mandatory=$true)][ValidateSet('medical','teaching')][string]$Kind, [switch]$Smoke)
& (Join-Path $PSScriptRoot 'Start-LocalModel.ps1') -Kind $Kind -Smoke:$Smoke
