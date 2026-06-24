@echo off
rem Beatex desktop app — double-click to run (no terminal needed).
rem Uses the app venv built per docs/model-setup.md / README "Setup".
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "app\qt_app.py"
