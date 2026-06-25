# Build Beatex.exe — a double-click launcher for the desktop GUI.
#
# Run from the repo root, inside the app venv:
#     .\scripts\build_exe.ps1
#
# NOTE: the exe bundles ONLY the GUI. Generation still needs the model env
# (external/Mapperatorinator + its Python 3.10 venv + weights) and ffmpeg on
# PATH. Keep Beatex.exe in the repo root so it finds external/ and data/.
$ErrorActionPreference = "Stop"
$py = ".venv\Scripts\python.exe"

& $py -m PyInstaller --noconfirm --onefile --windowed --name Beatex `
    --paths . `
    --hidden-import beatex.clicktrack `
    --hidden-import pydub `
    "app\qt_app.py"

Copy-Item -Force "dist\Beatex.exe" ".\Beatex.exe"
Write-Host "Built .\Beatex.exe  — keep it in the repo root (next to external/ and data/)."
