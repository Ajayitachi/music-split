@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: setting up, please wait...
    python -m venv .venv || (echo Python is not installed. Get it from python.org & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || (pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" multi_headphones.py
