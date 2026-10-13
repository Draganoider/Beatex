# Build Beatex.exe, a double-click launcher for Beatex Studio.
#
# Run from the repo root, inside the app venv (needs: pip install pyinstaller):
#     .\scripts\build_exe.ps1
#
# The exe bundles the Studio server + UI (no Python needed to start it) and
# opens the Studio in its own app window. Generation still needs the model env
# (external/Mapperatorinator + its Python 3.10 venv + weights) and ffmpeg on
# PATH. Keep Beatex.exe in the repo root so it finds external/ and data/.
$ErrorActionPreference = "Stop"
$py = ".venv\Scripts\python.exe"

& $py -m PyInstaller --noconfirm --onefile --windowed --name Beatex `
    --icon "app\studio\static\assets\beatex.ico" `
    --paths . `
    --add-data "app\studio\static;studio_static" `
    --hidden-import beatex.clicktrack `
    --hidden-import pydub `
    --hidden-import numpy `
    --exclude-module PyQt6 `
    --exclude-module streamlit `
    --exclude-module pandas `
    --exclude-module pyarrow `
    "app\studio\server.py"

Copy-Item -Force "dist\Beatex.exe" ".\Beatex.exe"
Write-Host "Built .\Beatex.exe  (keep it in the repo root, next to external/ and data/)."
