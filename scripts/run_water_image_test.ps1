param(
    [string]$InputRoot = "local_detection_samples\water_eval_inputs",
    [string]$EvalSize = "640x480",
    [int]$ImgSize = 320,
    [double]$MaxAreaRatio = 0.85,
    [double]$MaxMaskAreaRatio = 0.75,
    [switch]$Sensitive,
    [switch]$Show
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Model = "models\water_seg_v1.pt"
$OutputRoot = "local_detection_samples\water_eval"
$Extensions = @(".jpg", ".jpeg", ".png", ".bmp", ".webp")

if (-not (Test-Path $Model)) {
    throw "Missing model: $Model"
}

New-Item -ItemType Directory -Force -Path $InputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$Conf = 0.25
$MinAreaRatio = 0.002
$ModeName = "standard"
if ($Sensitive) {
    $Conf = 0.15
    $MinAreaRatio = 0.001
    $ModeName = "sensitive"
}

$Sets = @(
    @{ Name = "water_positive"; Tag = "water_positive" },
    @{ Name = "dry_negative"; Tag = "dry_negative" },
    @{ Name = "mixed_unknown"; Tag = "mixed_unknown" }
)

Write-Host "Water image test"
Write-Host "  model:      $Model"
Write-Host "  input root: $InputRoot"
Write-Host "  mode:       $ModeName"
Write-Host "  eval size:  $EvalSize"
Write-Host "  conf:       $Conf"
Write-Host "  min area:   $MinAreaRatio"
Write-Host "  max area:   $MaxAreaRatio"
Write-Host "  max mask:   $MaxMaskAreaRatio"
Write-Host ""

foreach ($Set in $Sets) {
    $Dir = Join-Path $InputRoot $Set.Name
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null

    $Images = Get-ChildItem -Path $Dir | Where-Object {
        -not $_.PSIsContainer -and $Extensions -contains $_.Extension.ToLowerInvariant()
    }

    if ($Images.Count -eq 0) {
        Write-Host "[skip] $($Set.Name): no images in $Dir"
        continue
    }

    $Tag = "$($Set.Tag)_$ModeName"
    Write-Host "[run] $($Set.Name): $($Images.Count) image(s)"

    $Args = @(
        "vision\water_eval.py",
        "--source", $Dir,
        "--model", $Model,
        "--tag", $Tag,
        "--eval-size", $EvalSize,
        "--imgsz", "$ImgSize",
        "--conf", "$Conf",
        "--min-area-ratio", "$MinAreaRatio",
        "--max-area-ratio", "$MaxAreaRatio",
        "--max-mask-area-ratio", "$MaxMaskAreaRatio",
        "--out-dir", $OutputRoot,
        "--save-all"
    )
    if ($Show) {
        $Args += "--show"
    }

    & python @Args
    if ($LASTEXITCODE -ne 0) {
        throw "water_eval failed for $($Set.Name)"
    }

    Write-Host ""
}

Write-Host "Done. Results are under:"
Write-Host "  $OutputRoot"
Write-Host ""
Write-Host "Open each latest <tag>_<timestamp>\summary.json and frames\*.jpg."
