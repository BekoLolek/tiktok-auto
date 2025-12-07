@echo off
echo Starting TikTok Uploader with visible browser...
echo.
echo When the browser opens:
echo 1. You will see the TikTok upload page (or login page)
echo 2. Log in with your TikTok account
echo 3. Make sure you can see the upload interface before closing
echo 4. Click "Allow all" for cookies if prompted
echo 5. Your session will be saved automatically
echo 6. Press Ctrl+C to stop when you see the upload form
echo.

REM Get the script directory
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..\..

REM Create session directory if it doesn't exist
if not exist "%PROJECT_DIR%\data\session" mkdir "%PROJECT_DIR%\data\session"

REM Set environment variables for local login
set BROWSER_HEADLESS=false
set SESSION_DIR=%PROJECT_DIR%\data\session
set TIKTOK_COOKIES_PATH=%PROJECT_DIR%\data\tiktok_cookies.json

cd /d "%SCRIPT_DIR%"
node src/index.js
pause
