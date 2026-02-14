@echo off
setlocal

chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

cd /d %~dp0
pushd backend

set "PYTHON_EXE="
for /f "delims=" %%I in ('py -3.10 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"

if not defined PYTHON_EXE (
  echo Python 3.10 not found. Please install Python 3.10 and try again.
  goto :error
)

if exist ".venv\Scripts\python.exe" (
  echo Using existing virtual environment...
) else (
  echo Creating virtual environment...
  "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"

set "OUTLOOK_DEVICE_AUTHORITY=https://login.microsoftonline.com/consumers/"
set "OUTLOOK_DEVICE_SCOPES=User.Read Mail.Read Mail.ReadWrite Mail.Send"
echo Outlook device authority: %OUTLOOK_DEVICE_AUTHORITY%
echo Outlook device scopes   : %OUTLOOK_DEVICE_SCOPES%

echo Installing backend dependencies (Tsinghua mirror)...
python -m pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :error
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :pip_error


echo Starting backend...
python app.py

popd
endlocal
exit /b 0

:pip_error
echo Dependency install failed.
echo If you see "Failed building wheel for cchardet", install Python 3.10 or 3.9,
echo delete .venv, then run this script again.
popd
endlocal
exit /b 1

:error
echo Backend startup failed.
popd
endlocal
exit /b 1
