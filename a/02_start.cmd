@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (echo Run a\01_install.cmd first. & pause & exit /b 1)
.venv\Scripts\python.exe a\lab_server.py --open-browser
pause
