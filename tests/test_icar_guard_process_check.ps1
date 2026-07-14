$ErrorActionPreference = 'Stop'

$guard = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_guard.sh')

if ($guard -notmatch 'icar_startup\.sh') {
    throw 'icar_guard must skip while icar_startup.sh is active.'
}

if ($guard -match [regex]::Escape('ps -eo stat=,args= | grep -F')) {
    throw 'icar_guard process count includes its own shell/grep inspector.'
}

if ($guard -notmatch [regex]::Escape('!~ /^(python3|python|ros2|bash|sh|awk|grep|ps)$/')) {
    throw 'icar_guard process count must exclude wrapper and inspector processes.'
}

Write-Output 'PASS: icar_guard process checks are isolated from startup and inspectors.'
