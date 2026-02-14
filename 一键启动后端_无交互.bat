@echo off
setlocal EnableExtensions

chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

cd /d %~dp0
pushd backend

set "PYTHON_EXE="
for /f "delims=" %%I in ('py -3.10 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"

if not defined PYTHON_EXE (
  echo [ERROR] Python 3.10 not found. Please install Python 3.10 and try again.
  goto :error
)

if exist ".venv\Scripts\python.exe" (
  echo [INFO] Using existing virtual environment.
) else (
  echo [INFO] Creating virtual environment...
  "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

set "OUTLOOK_DEVICE_AUTHORITY=https://login.microsoftonline.com/consumers/"
set "OUTLOOK_DEVICE_SCOPES=User.Read Mail.Read Mail.ReadWrite Mail.Send"

echo [INFO] Outlook device authority: %OUTLOOK_DEVICE_AUTHORITY%
echo [INFO] Outlook device scopes   : %OUTLOOK_DEVICE_SCOPES%

echo [INFO] Installing/updating backend dependencies...
python -m pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :error
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :error

if not exist "logs" mkdir logs
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format ''yyyyMMdd-HHmmss''"') do set "TS=%%I"
set "LOG_FILE=%cd%\logs\backend-%TS%.log"

echo [INFO] Starting backend in background...
start "FireMail Backend" /min cmd /c "cd /d %cd% && call .venv\Scripts\activate.bat && set PYTHONIOENCODING=utf-8 && set PYTHONUTF8=1 && set PYTHONUNBUFFERED=1 && set OUTLOOK_DEVICE_AUTHORITY=%OUTLOOK_DEVICE_AUTHORITY% && set OUTLOOK_DEVICE_SCOPES=%OUTLOOK_DEVICE_SCOPES% && python app.py >> ""%LOG_FILE%"" 2>&1"
if errorlevel 1 goto :error

echo [OK] Backend started.
echo [OK] Log file: %LOG_FILE%
echo.
echo [TIP] To watch logs:
echo powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Wait -Encoding UTF8"

popd
endlocal
exit /b 0

:error
echo [ERROR] Backend startup failed.
popd
endlocal
exit /b 1

