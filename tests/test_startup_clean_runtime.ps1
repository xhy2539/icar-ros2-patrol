$ErrorActionPreference = 'Stop'

$script = Get-Content -Raw (Join-Path $PSScriptRoot '..\scripts\icar_startup.sh')

if ($script -notmatch 'docker restart autodrive_ros2') {
    throw 'Startup must restart autodrive_ros2 once to clear unreaped vendor ROS children before n1.'
}

if ($script -notmatch [regex]::Escape('!~ /^(python3|python|ros2|bash|sh|awk)$/')) {
    throw 'Process singleton checks must exclude python/ros2 wrapper processes.'
}

if ($script -notmatch [regex]::Escape("pkill -f '[d]ocker exec icar_ros2 .*llm_gateway'")) {
    throw 'Startup must clear stale host docker exec llm_gateway wrappers.'
}

if ($script -notmatch [regex]::Escape("pkill -f '[d]ocker exec icar_ros2 .*cloud_bridge'")) {
    throw 'Startup must clear stale host docker exec cloud_bridge wrappers.'
}

if ($script -notmatch [regex]::Escape("pkill -f '[r]os2 run llm_gateway llm_gateway_node'")) {
    throw 'Startup must clear stale container ros2 run llm_gateway wrappers.'
}

if ($script -match [regex]::Escape('ps -eo stat=,args= | grep -F')) {
    throw 'Process singleton checks must not count their own shell/grep inspector.'
}

Write-Output 'PASS: startup clears orphaned ROS children and counts real node executables only.'
