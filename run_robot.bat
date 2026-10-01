@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Project virtual environment not found: "%~dp0.venv\Scripts\python.exe"
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
exit /b %errorlevel%
