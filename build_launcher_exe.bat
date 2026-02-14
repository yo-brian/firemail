@echo off
setlocal

chcp 65001 >nul
cd /d %~dp0
set "LOG_FILE=%~dp0build_launcher.log"
echo ===== %date% %time% ===== > "%LOG_FILE%"
echo Working dir: %cd%>> "%LOG_FILE%"

echo [1/3] Checking Python...
py -3 -V >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo Python launcher "py" not found. Please install Python 3.
  echo ERROR: Python launcher "py" not found.>> "%LOG_FILE%"
  echo Log file: %LOG_FILE%
  pause
  exit /b 1
)

echo [2/3] Installing/Updating PyInstaller...
py -3 -m pip install --upgrade pyinstaller >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo Failed to install PyInstaller.
  echo ERROR: Failed to install PyInstaller.>> "%LOG_FILE%"
  echo Log file: %LOG_FILE%
  pause
  exit /b 1
)

echo [3/3] Building EXE...
py -3 -m PyInstaller --noconfirm --onefile --windowed --name FireMailLauncher --distpath "%~dp0dist" --workpath "%~dp0build" "%~dp0launcher_gui.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo Build failed.
  echo ERROR: Build failed.>> "%LOG_FILE%"
  echo Log file: %LOG_FILE%
  pause
  exit /b 1
)

if exist "%~dp0dist\一键启动前后端.exe" del /f /q "%~dp0dist\一键启动前后端.exe"
ren "%~dp0dist\FireMailLauncher.exe" "一键启动前后端.exe"
if errorlevel 1 (
  echo Rename failed. Keeping default file name: FireMailLauncher.exe
  echo WARN: Rename failed. Keeping default file name: FireMailLauncher.exe>> "%LOG_FILE%"
  if exist "%~dp0dist\FireMailLauncher.exe" (
    echo Build success: %~dp0dist\FireMailLauncher.exe
    echo Log file: %LOG_FILE%
    pause
    exit /b 0
  ) else (
    echo Build output not found.
    echo ERROR: Build output not found.>> "%LOG_FILE%"
    echo Log file: %LOG_FILE%
    pause
    exit /b 1
  )
)

echo Build success: %~dp0dist\一键启动前后端.exe
echo Please keep this EXE in the project root folder together with:
echo - 一键启动后端.bat
echo - 一键启动前端.bat
echo Log file: %LOG_FILE%
pause
exit /b 0
