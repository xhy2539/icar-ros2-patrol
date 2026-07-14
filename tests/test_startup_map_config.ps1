$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')
$expected = '/root/yahboomcar_ros2_ws/yahboomcar_ws/install/yahboomcar_nav/share/yahboomcar_nav/maps/yahboomcar.yaml'

if ($script -notmatch [regex]::Escape($expected)) {
    throw "Startup must default to the installed map metadata that matches the calibrated patrol points."
}

if ($script -match '/src/yahboomcar_nav/maps/yahboomcar\.yaml') {
    throw 'Startup must not default to the source-tree map YAML with incompatible origin metadata.'
}

Write-Output 'PASS: startup defaults to the calibrated installed map YAML.'
