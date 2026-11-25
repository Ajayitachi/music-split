@echo off
rem Builds the Windows app into dist\MultiHeadphones\ and zips it with the installer.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt -r requirements-build.txt || (pause & exit /b 1)
".venv\Scripts\python.exe" tools\make_icon.py || (pause & exit /b 1)
".venv\Scripts\pyinstaller.exe" --noconfirm --clean MultiHeadphones.spec || (pause & exit /b 1)
copy /y installer\Install.bat dist\MultiHeadphones\ >nul
copy /y installer\install.ps1 dist\MultiHeadphones\ >nul
copy /y installer\uninstall.ps1 dist\MultiHeadphones\ >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\MultiHeadphones' -DestinationPath 'dist\MultiHeadphones-Windows.zip'"
echo.
echo Done: dist\MultiHeadphones\MultiHeadphones.exe
echo Share: dist\MultiHeadphones-Windows.zip  (unzip, then double-click Install.bat)
