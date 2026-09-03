# Build a portable, self-contained T4A-BORIS folder for Windows end users.
#
# Adapted from windows_deployment.ps1 (upstream's own portable-zip builder): same standalone
# Python + PySide6/mpv bundling approach, but installs THIS FORK from source instead of
# `pip install boris-behav-obs` from PyPI - upstream's script pulls the public package, which
# would give end users vanilla BORIS, not the model-import/stamping features built here.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\deployment\t4a_boris_windows_deployment.ps1
#
# By default installs from the local repo checkout (whatever is currently on disk, including
# uncommitted changes) - fine for building/testing this pipeline. For a real release build, pass
# -Source with a git URL pinned to a specific commit/tag instead, e.g.:
#   -Source "git+https://github.com/Nareed/BORIS.git@<commit-or-tag>"

param(
    [string]$Source = (Resolve-Path "$PSScriptRoot\..\..").Path,
    [string]$AppName = "T4A-BORIS",
    # libmpv-2.dll + ffmpeg.exe + ffprobe.exe: BORIS auto-downloads these on first run if
    # missing (see boris/utilities.py) - showing an "MPV library was not found, downloading..."
    # dialog and a real wait, and needing internet access, the moment a non-technical end user
    # first opens the app. Pre-bundling them (copied from a local checkout that's already run
    # BORIS once, so they exist at boris/misc/) means that first-run download never triggers.
    [string]$MiscSourceDir = (Join-Path (Resolve-Path "$PSScriptRoot\..\..").Path "boris\misc")
)

$Url = "https://github.com/astral-sh/python-build-standalone/releases/download/20251014/cpython-3.13.9+20251014-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
$DownloadPath = "$env:TEMP\cpython-3.13.9.tar.gz"
$ExtractPath = "$env:USERPROFILE\$AppName-build"

if (Test-Path $ExtractPath) {
    Write-Host "Removing existing $AppName build folder at $ExtractPath..."
    Remove-Item -Path $ExtractPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ExtractPath | Out-Null

Write-Host "Downloading standalone Python build..."
Invoke-WebRequest -Uri $Url -OutFile $DownloadPath

Write-Host "Download complete. Extracting..."
& tar -xzf $DownloadPath -C $ExtractPath

$PythonExe = Get-ChildItem -Path $ExtractPath -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-Not $PythonExe) {
    Write-Error "Python executable not found after extraction!"
    exit 1
}

& "$($PythonExe.FullName)" -m ensurepip --upgrade
& "$($PythonExe.FullName)" -m pip install --upgrade pip

# Install from a built wheel rather than `pip install <source dir>` directly: installing straight
# from a local source tree re-runs setuptools package *discovery* against whatever happens to be
# sitting in the repo root at build time (hit a real "Multiple top-level packages discovered in a
# flat-layout" failure from a stray empty directory this way) - a wheel is already a resolved
# package list, so it can't have that problem. Matches how this project's own justfile builds
# releases (`uv build`) rather than reinventing packaging here.
if ($Source -like "git+*" -or $Source -like "http*") {
    Write-Host "Installing $AppName from: $Source"
    & "$($PythonExe.FullName)" -m pip install $Source
} else {
    Write-Host "Building a wheel from: $Source"
    $WheelDir = "$env:TEMP\t4a-boris-wheel-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null
    Push-Location $Source
    try {
        uv build --wheel --out-dir $WheelDir
        if ($LASTEXITCODE -ne 0) { throw "uv build failed" }
    } finally {
        Pop-Location
    }
    $Wheel = Get-ChildItem -Path $WheelDir -Filter "*.whl" | Select-Object -First 1
    if (-not $Wheel) { Write-Error "No wheel produced by uv build"; exit 1 }
    Write-Host "Installing wheel: $($Wheel.Name)"
    & "$($PythonExe.FullName)" -m pip install "$($Wheel.FullName)"
}

# Pre-bundle libmpv/ffmpeg/ffprobe so the app never needs to auto-download them on first run.
# They land in <bundle>\python\Lib\site-packages\boris\misc\ - the exact path
# Path(__file__).parent / "misc" resolves to once boris is installed there (utilities.py), and
# core.py already prepends that directory to PATH before anything imports it, so simply having
# the files present is enough - no code change needed, just getting them there before first launch.
$BorisMiscDir = Join-Path $ExtractPath "python\Lib\site-packages\boris\misc"
$RequiredMiscFiles = @("libmpv-2.dll", "ffmpeg.exe", "ffprobe.exe")
$MissingMiscFiles = $RequiredMiscFiles | Where-Object { -not (Test-Path (Join-Path $MiscSourceDir $_)) }
if ($MissingMiscFiles) {
    Write-Error "Missing from ${MiscSourceDir}: $($MissingMiscFiles -join ', '). Run BORIS once from a dev checkout first so it auto-downloads them, or pass -MiscSourceDir pointing at a folder that already has them."
    exit 1
}
Write-Host "Bundling libmpv/ffmpeg/ffprobe from $MiscSourceDir (no first-run download needed)..."
New-Item -ItemType Directory -Force -Path $BorisMiscDir | Out-Null
foreach ($f in $RequiredMiscFiles) {
    Copy-Item -Path (Join-Path $MiscSourceDir $f) -Destination $BorisMiscDir -Force
}

# Strip unused files/plugins (same trims as upstream's script - smaller bundle, faster install)
$TrimPaths = @(
    "python\tcl", "python\include", "python\share",
    "python\Lib\ensurepip", "python\Lib\pydoc_data", "python\Lib\tkinter",
    "python\Lib\turtledemo", "python\Lib\venv", "python\Scripts",
    "python\Lib\site-packages\PySide6\glue",
    "python\Lib\site-packages\PySide6\plugins\geoservices",
    "python\Lib\site-packages\PySide6\plugins\multimedia",
    "python\Lib\site-packages\PySide6\plugins\qmltooling",
    "python\Lib\site-packages\PySide6\plugins\sensors",
    "python\Lib\site-packages\PySide6\plugins\sqldrivers",
    "python\Lib\site-packages\PySide6\plugins\texttospeech",
    "python\Lib\site-packages\PySide6\qml",
    "python\Lib\site-packages\PySide6\translations",
    "python\Lib\site-packages\PySide6\assistant.exe",
    "python\Lib\site-packages\PySide6\designer.exe",
    "python\Lib\site-packages\PySide6\linguist.exe",
    "python\Lib\site-packages\PySide6\qmlformat.exe",
    "python\Lib\site-packages\PySide6\Qt6Quick.dll",
    "python\Lib\site-packages\PySide6\Qt6Pdf.dll",
    "python\Lib\site-packages\PySide6\Qt6Designer.dll",
    "python\Lib\site-packages\PySide6\Qt6Qml.dll",
    "python\Lib\site-packages\PySide6\Qt6Quick3DRuntimeRender.dll",
    "python\Lib\site-packages\PySide6\Qt6WebEngineCore.dll",
    "python\Lib\site-packages\PySide6\Qt6WebEngineQuick.dll",
    "python\Lib\site-packages\PySide6\Qt6WebEngineQuickDelegatesQml.dll",
    "python\Lib\site-packages\PySide6\Qt6WebEngineWidgets.dll"
)
foreach ($p in $TrimPaths) {
    $full = Join-Path $ExtractPath $p
    if (Test-Path $full) { Remove-Item -Path $full -Recurse -Force }
}

Write-Host "`nInstallation complete!"
$BorisVersionOutput = & "$($PythonExe.FullName)" -m boris -v 2>$null
$BorisVersion = ($BorisVersionOutput | Select-String -Pattern '\b\d+\.\d+(?:\.\d+)?\b').Matches.Value
if (-not $BorisVersion) {
    Write-Warning "Could not determine version, defaulting to 'unknown'"
    $BorisVersion = "unknown"
}
Write-Host "Detected version: $BorisVersion"

# Smoke test: launch briefly and confirm it stays running, without blocking the build waiting
# for a human to close the window (unlike upstream's script, meant for interactive maintainer
# use - this one also runs from automation).
Write-Host "`nSmoke-testing the build (launching briefly)..."
$smokeProc = Start-Process -FilePath "$($PythonExe.FullName)" -ArgumentList "-m","boris" -PassThru
Start-Sleep -Seconds 6
if (Get-Process -Id $smokeProc.Id -ErrorAction SilentlyContinue) {
    Write-Host "Smoke test OK - still running, closing it now."
    Stop-Process -Id $smokeProc.Id -Force
} else {
    Write-Error "Smoke test FAILED - the app exited on its own. Aborting build."
    exit 1
}

$OutDir = "$env:USERPROFILE\$AppName-$BorisVersion-build-output"
if (Test-Path $OutDir) { Remove-Item -Path $OutDir -Recurse -Force }
Rename-Item -Path $ExtractPath -NewName (Split-Path $OutDir -Leaf)

Write-Host "`nBuild output folder: $OutDir"
Write-Host "Next: run the Inno Setup script (t4a_boris_installer.iss) against this folder to produce Setup.exe."
