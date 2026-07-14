$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

if ($script -match 'static_transform_publisher\s+0\s+0\s+0\.12\s+0\s+0\s+0\s+base_link\s+laser') {
    throw 'Startup must not publish a second base_link -> laser transform; vendor n1 owns the laser TF.'
}

if ($script -notmatch 'n1 is the vendor-provided interactive shortcut' -or $script -notmatch 'base_link -> laser TF chain') {
    throw 'Startup should document that n1 owns chassis, lidar, EKF, and laser TF.'
}

Write-Output 'PASS: startup leaves base_link -> laser TF ownership to n1.'
