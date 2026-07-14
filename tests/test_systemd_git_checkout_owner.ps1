$ErrorActionPreference = 'Stop'

$startup = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.service')
$web = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_web_gateway.service')

if ($startup -match 'icar-deploy/current') {
    throw 'icar_startup.service must use the Git checkout, not icar-deploy/current.'
}

if ($web -match 'icar-deploy/current') {
    throw 'icar_web_gateway.service must use the Git checkout, not icar-deploy/current.'
}

if ($startup -notmatch [regex]::Escape('ExecStart=/bin/bash /home/jetson/icar-ros2-patrol/scripts/icar_startup.sh')) {
    throw 'icar_startup.service must start the Git checkout startup script directly.'
}

if ($web -notmatch [regex]::Escape('ExecStart=/usr/bin/python3 /home/jetson/icar-ros2-patrol/app/web_gateway.py')) {
    throw 'icar_web_gateway.service must start the Git checkout web gateway directly.'
}

if ($startup -notmatch 'Restart=no') {
    throw 'icar_startup.service must not auto-retry the oneshot startup.'
}

Write-Output 'PASS: systemd units use the Git checkout as the runtime source.'
