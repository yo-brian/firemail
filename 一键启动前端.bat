@echo off
setlocal

cd /d %~dp0
pushd frontend

if not exist "node_modules" (
  echo Installing frontend dependencies...
  npm install
  if errorlevel 1 goto :error
)

echo Starting frontend dev server...
npm run dev

popd
endlocal
exit /b 0

:error
echo Frontend startup failed.
popd
endlocal
exit /b 1
