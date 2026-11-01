@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe goto dependencies
where py >nul 2>nul
if errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
if errorlevel 1 goto fail
:dependencies
.venv\Scripts\python.exe -m pip install -r c\voice-camera-notes\requirements.txt
if errorlevel 1 goto fail
echo Installation complete. Run a\02_start.cmd
pause
exit /b 0
:fail
echo Installation failed. Check Python 3.11+ and network, then retry.
pause
exit /b 1
