@echo off
setlocal EnableDelayedExpansion

chcp 65001 >nul

set "API_URL=http://localhost:5000"
set "WS_HOST=localhost"
set "WS_PORT=8765"
set "TMP_DIR=%TEMP%\firemail_test"
if not exist "%TMP_DIR%" mkdir "%TMP_DIR%"

set "LOGIN_JSON=%TMP_DIR%\login.json"
set "IMAP_JSON=%TMP_DIR%\imap_test.json"
set "CHECK_JSON=%TMP_DIR%\check_email.json"
set "AUTH_USER_JSON=%TMP_DIR%\auth_user.json"
set "EMAILS_JSON=%TMP_DIR%\emails.json"

set "TOKEN="

:menu
cls

echo === FireMail Test Menu ===
echo API: %API_URL%
echo WS:  ws://%WS_HOST%:%WS_PORT%
echo.
echo 1. Basic HTTP health/config
echo 2. Login (get token)
echo 3. Auth user (requires token)
echo 4. List emails (requires token)
echo 5. IMAP test connection (requires token)
echo 6. Check email by ID (requires token)
echo 7. WebSocket port check
if defined TOKEN (
  echo Token: SET
) else (
  echo Token: NOT SET
)
echo.
set /p CHOICE=Select option (1-7, a=all, q=quit): 

if /i "%CHOICE%"=="q" goto :eof
if /i "%CHOICE%"=="a" goto :all
if "%CHOICE%"=="1" goto :basic
if "%CHOICE%"=="2" goto :login
if "%CHOICE%"=="3" goto :auth_user
if "%CHOICE%"=="4" goto :list_emails
if "%CHOICE%"=="5" goto :imap_test
if "%CHOICE%"=="6" goto :check_email
if "%CHOICE%"=="7" goto :ws_check

echo Invalid choice.
pause
goto :menu

:all
call :basic
call :login
call :auth_user
call :list_emails
call :imap_test
call :check_email
call :ws_check
pause
goto :menu

:basic
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found. Skipping HTTP tests.
  goto :eof
)

echo [HTTP] /api/health
curl -s -o nul -w "status=%%{http_code}\n" "%API_URL%/api/health"

echo [HTTP] /api/config
curl -s -o nul -w "status=%%{http_code}\n" "%API_URL%/api/config"

goto :eof

:login
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found. Skipping login.
  goto :eof
)
set /p USERNAME=Login username: 
set /p PASSWORD=Login password: 
set "LOGIN_BODY={\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}"

curl -s -H "Content-Type: application/json" -d "%LOGIN_BODY%" "%API_URL%/api/auth/login" > "%LOGIN_JSON%"
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "try { (Get-Content -Raw '%LOGIN_JSON%' | ConvertFrom-Json).token } catch { '' }"`) do set "TOKEN=%%T"

if "%TOKEN%"=="" (
  echo [AUTH] Login failed. Response:
  type "%LOGIN_JSON%"
) else (
  echo [AUTH] Login OK. Token set.
)

goto :eof

:auth_user
if not defined TOKEN (
  echo [AUTH] Token not set. Run login first.
  goto :eof
)
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found.
  goto :eof
)

curl -s -H "Authorization: Bearer %TOKEN%" "%API_URL%/api/auth/user" > "%AUTH_USER_JSON%"
echo [AUTH] User response:
type "%AUTH_USER_JSON%"

goto :eof

:list_emails
if not defined TOKEN (
  echo [AUTH] Token not set. Run login first.
  goto :eof
)
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found.
  goto :eof
)

curl -s -H "Authorization: Bearer %TOKEN%" "%API_URL%/api/emails" > "%EMAILS_JSON%"
echo [EMAILS] List response:
type "%EMAILS_JSON%"

goto :eof

:imap_test
if not defined TOKEN (
  echo [AUTH] Token not set. Run login first.
  goto :eof
)
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found.
  goto :eof
)

echo [IMAP] Test connection
set /p IMAP_EMAIL=Email: 
set /p IMAP_PASSWORD=Password: 
set /p IMAP_SERVER=Server (blank for auto): 
set /p IMAP_PORT=Port (default 993): 
if "%IMAP_PORT%"=="" set "IMAP_PORT=993"
set /p IMAP_SSL=Use SSL? (true/false, default true): 
if "%IMAP_SSL%"=="" set "IMAP_SSL=true"

set "IMAP_BODY={\"email\":\"%IMAP_EMAIL%\",\"password\":\"%IMAP_PASSWORD%\",\"server\":\"%IMAP_SERVER%\",\"port\":%IMAP_PORT%,\"use_ssl\":%IMAP_SSL%}"

REM This endpoint may not exist in current backend; will show response if 404
curl -s -H "Content-Type: application/json" -H "Authorization: Bearer %TOKEN%" -d "%IMAP_BODY%" "%API_URL%/api/emails/test-connection" > "%IMAP_JSON%"

echo [IMAP] Test response:
type "%IMAP_JSON%"

goto :eof

:check_email
if not defined TOKEN (
  echo [AUTH] Token not set. Run login first.
  goto :eof
)
where curl >nul 2>nul
if errorlevel 1 (
  echo [WARN] curl not found.
  goto :eof
)

echo [EMAIL] Check mailbox by ID
set /p EMAIL_ID=Email ID: 
if "%EMAIL_ID%"=="" goto :eof

curl -s -H "Content-Type: application/json" -H "Authorization: Bearer %TOKEN%" -d "{}" "%API_URL%/api/emails/%EMAIL_ID%/check" > "%CHECK_JSON%"

echo [EMAIL] Check response:
type "%CHECK_JSON%"

goto :eof

:ws_check
echo [WS] port check %WS_HOST%:%WS_PORT%
powershell -NoProfile -Command "try { $r=Test-NetConnection -ComputerName '%WS_HOST%' -Port %WS_PORT%; if ($r.TcpTestSucceeded) { 'status=200' } else { 'status=FAILED' } } catch { 'status=ERROR' }"

goto :eof
