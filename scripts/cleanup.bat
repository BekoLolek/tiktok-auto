@echo off
REM TikTok Auto - Cleanup Old Files
REM Usage: Double-click to remove files older than 7 days

cd /d "%~dp0.."

echo TikTok Auto - File Cleanup
echo ==========================
echo.
echo This will delete files older than 7 days from:
echo   - data\audio
echo   - data\videos
echo   - data\scripts
echo.

set /p confirm="Are you sure you want to continue? (yes/no): "
if /i not "%confirm%"=="yes" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Cleaning audio files...
forfiles /p "data\audio" /s /m *.* /d -7 /c "cmd /c del @path" 2>nul
echo Cleaning video files...
forfiles /p "data\videos" /s /m *.* /d -7 /c "cmd /c del @path" 2>nul
echo Cleaning script files...
forfiles /p "data\scripts" /s /m *.* /d -7 /c "cmd /c del @path" 2>nul

echo.
echo Cleaning Docker resources...
docker system prune -f

echo.
echo Cleanup complete!
echo.
pause
