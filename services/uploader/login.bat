@echo off
echo Starting TikTok Uploader with visible browser...
echo.
echo When the browser opens:
echo 1. Navigate to tiktok.com
echo 2. Log in with your TikTok account
echo 3. Your session will be saved automatically
echo 4. Press Ctrl+C to stop the server when done
echo.
set BROWSER_HEADLESS=false
node src/index.js
