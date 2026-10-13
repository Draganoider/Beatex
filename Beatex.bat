@echo off
rem Beatex Studio: double-click to open the desktop app (no terminal needed).
rem Uses the app venv built per README "Setup". Closing the window stops the server.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "app\studio\server.py" --app
