$launchPath = Join-Path $PSScriptRoot '..\app_control\launch\navigation_mux.launch.py'
$launch = Get-Content -Raw $launchPath

# The vendor n1 (laser_bringup_launch.py) owns base_link -> laser.  Starting
# another publisher here would make the navigation stack have two TF owners.
if ($launch -match 'static_transform_publisher') {
  throw 'navigation_mux must not publish base_link -> laser; n1 owns that transform.'
}

Write-Output 'PASS: navigation_mux leaves base_link -> laser ownership to n1.'
