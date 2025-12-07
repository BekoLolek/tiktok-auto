@echo off
echo Exporting TikTok cookies from your Chrome browser...
echo.
echo IMPORTANT: Close all Chrome windows first!
echo.
pause

REM Get the script directory
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..\..

REM Create data directory if it doesn't exist
if not exist "%PROJECT_DIR%\data" mkdir "%PROJECT_DIR%\data"

REM Set environment variables
set TIKTOK_COOKIES_PATH=%PROJECT_DIR%\data\tiktok_cookies.json
set USE_CHROME_PROFILE=true
set CHROME_USER_DATA=C:\Users\L\AppData\Local\Google\Chrome\User Data

cd /d "%SCRIPT_DIR%"
node src/export-cookies.js
pause
