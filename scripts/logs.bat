@echo off
REM TikTok Auto - View Logs
REM Usage: logs.bat [service]
REM Examples: logs.bat dashboard, logs.bat uploader

cd /d "%~dp0.."

if "%1"=="" (
    echo Showing all logs (Ctrl+C to exit)...
    echo.
    docker compose logs -f --tail=100
) else (
    echo Showing %1 logs (Ctrl+C to exit)...
    echo.
    docker compose logs -f --tail=100 %1
)
