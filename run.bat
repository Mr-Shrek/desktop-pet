@echo off
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python main.py
    exit /b
)

echo [ERROR] Python not found.
echo Please install Python 3 from https://www.python.org/downloads/
echo This pet uses only Python standard library, no third-party dependencies.
pause
