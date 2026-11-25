@echo off
rem Run from source (for development). Normal users: install the app with build.bat / Install.bat.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: setting up, please wait...
    python -m venv .venv || (echo Python is not installed. Get it from python.org & pause & exit /b 1)
)
".venv\Scripts\python.exe" -c "import soundcard, numpy, sv_ttk" 2>nul || (
    echo Installing what the app needs, please wait...
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || (pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" multi_headphones.py
