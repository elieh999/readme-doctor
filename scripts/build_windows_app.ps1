# Builds the standalone Windows desktop application with PyInstaller.
#
# Run from a development checkout that has the dev extra installed:
#   powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$entryPoint = Join-Path $projectRoot "src\readme_doctor\gui.py"
$applicationDirectory = Join-Path $projectRoot "Application"
$buildDirectory = Join-Path $projectRoot "work\pyinstaller"

# Prefer the project virtual environment so the build uses the pinned dependency set rather than
# whatever interpreter happens to be first on PATH.
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
    Write-Host "No .venv found, using the interpreter on PATH."
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: $python -m pip install -e `".[dev]`""
}

& $python -m PyInstaller `
    --name "README Doctor" `
    --onefile `
    --windowed `
    --clean `
    --noconfirm `
    --distpath $applicationDirectory `
    --workpath $buildDirectory `
    --specpath $buildDirectory `
    $entryPoint

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

# The intermediate build tree is large and is not needed once the executable exists.
if (Test-Path (Join-Path $projectRoot "work")) {
    Remove-Item -Recurse -Force (Join-Path $projectRoot "work")
}

$executable = Join-Path $applicationDirectory "README Doctor.exe"
$sizeMb = [Math]::Round((Get-Item $executable).Length / 1MB, 1)
Write-Host "Built $executable ($sizeMb MB)"
