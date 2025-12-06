@echo off
REM TikTok Auto - Backup Database
REM Usage: Double-click to create a database backup

cd /d "%~dp0.."

echo TikTok Auto - Database Backup
echo ==============================
echo.

REM Create backup directory
if not exist data\backups mkdir data\backups

REM Get timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /format:list') do set datetime=%%I
set timestamp=%datetime:~0,8%_%datetime:~8,6%
set backup_file=data\backups\tiktok_auto_%timestamp%.sql

echo Creating backup: %backup_file%
echo.

docker compose exec -T postgres pg_dump -U tiktok_auto -d tiktok_auto > "%backup_file%"

if %errorlevel% equ 0 (
    echo.
    echo Backup created successfully!
    echo File: %backup_file%
) else (
    echo.
    echo Backup failed!
)

echo.
pause
