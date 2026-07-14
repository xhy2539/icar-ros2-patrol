$ErrorActionPreference = 'Stop'

$startup = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

if ($startup -notmatch 'exec 9>&-') {
    throw 'Background long-lived startup commands must close lock fd 9 before exec.'
}

if ($startup -match "nohup docker exec autodrive_ros2 bash -ic 'n1'\s*``?r?``?n\s*</dev/null") {
    throw 'n1 docker exec inherits /run/icar_startup.lock; close fd 9 in a subshell first.'
}

Write-Output 'PASS: startup background processes do not retain the startup lock.'
