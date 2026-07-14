$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

foreach ($process in @(
    '/nav2_map_server/map_server',
    '/nav2_amcl/amcl',
    '/nav2_controller/controller_server',
    '/nav2_planner/planner_server'
)) {
    if ($script -notmatch [regex]::Escape("require_single_process autodrive_ros2 '$process'")) {
        throw "Startup must verify exactly one Nav2 process: $process"
    }
}

if ($script -notmatch [regex]::Escape("require_process_count autodrive_ros2 '/nav2_lifecycle_manager/lifecycle_manager' lifecycle_manager 2")) {
    throw 'Startup must verify the two expected Nav2 lifecycle managers, with no duplicates.'
}

Write-Output 'PASS: startup verifies a single Nav2 process set.'
