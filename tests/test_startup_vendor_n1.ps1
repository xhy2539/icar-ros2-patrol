$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

if ($script -notmatch "nohup docker exec autodrive_ros2 bash -ic 'n1'") {
    throw 'Startup must launch the vendor base/lidar stack through the autodrive container n1 alias.'
}

if ($script -match 'ros2 launch yahboomcar_bringup yahboomcar_bringup_X3_launch\.py') {
    throw 'Startup must not bypass n1 with a second manual chassis bringup launch.'
}

if ($script -match 'ros2 launch sllidar_ros2 sllidar_launch\.py') {
    throw 'Startup must not launch lidar separately; n1 owns it.'
}

Write-Output 'PASS: startup uses n1 as the sole vendor chassis/lidar entrypoint.'
