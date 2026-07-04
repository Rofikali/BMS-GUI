$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$BuildDir = if ($env:BMS_BUILD_DIR) { $env:BMS_BUILD_DIR } else { Join-Path $RootDir "build/verify" }

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "bms-gui-uv-cache"
}
if (-not $env:QT_QPA_PLATFORM) {
    $env:QT_QPA_PLATFORM = "offscreen"
}

if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    Write-Error "cmake is required to verify BMS-GUI"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is required to run the Python verification gate"
}

$GeneratorArgs = @()
if ($env:CMAKE_GENERATOR) {
    $GeneratorArgs = @("-G", $env:CMAKE_GENERATOR)
}
elseif (Get-Command ninja -ErrorAction SilentlyContinue) {
    $GeneratorArgs = @("-G", "Ninja")
}

$GeneratorLabel = if ($GeneratorArgs.Count -gt 0) { $GeneratorArgs[-1] } else { "CMake default" }
Write-Host "==> Configuring native core ($GeneratorLabel)"
& cmake -S $RootDir -B $BuildDir @GeneratorArgs

Write-Host "==> Building native core"
& cmake --build $BuildDir

Write-Host "==> Running native tests"
& ctest --test-dir $BuildDir --output-on-failure

Write-Host "==> Running Python tests"
Push-Location $RootDir
try {
    & uv run python -m unittest discover tests

    Write-Host "==> Running MVP release check"
    & uv run bms-release-check
}
finally {
    Pop-Location
}

Write-Host "==> Verification passed"
