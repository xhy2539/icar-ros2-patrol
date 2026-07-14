$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

if ($script -match 'nav2_bridge_node --mode real') {
    throw 'Nav2-enabled startup must not launch nav2_bridge_node --mode real; nav2_goal_adapter is the single real Nav2 feedback owner.'
}

if ($script -notmatch 'nav2_bridge_node --mode mock') {
    throw 'Nav2-disabled startup must keep nav2_bridge_node --mode mock as the fallback /goal_pose -> /nav_status bridge.'
}

if ($script -notmatch 'navigation_mux\.launch\.py') {
    throw 'Nav2-enabled startup must still launch navigation_mux.launch.py, which owns nav2_goal_adapter_node.'
}

if ($script -notmatch [regex]::Escape("require_single_process autodrive_ros2 '/root/icar_app_ws/install/app_control/lib/app_control/nav2_goal_adapter_node' nav2_goal_adapter")) {
    throw 'Nav2-enabled startup must verify nav2_goal_adapter as the single real /nav_status publisher.'
}

Write-Output 'PASS: startup has one real Nav2 feedback owner and keeps the mock fallback.'
