@echo off
REM TikTok Auto - Restore Database
REM Usage: restore.bat backup_file.sql

cd /d "%~dp0.."

echo TikTok Auto - Database Restore
echo ===============================
echo.

if "%1"=="" (
    echo Usage: restore.bat [backup_file]
    echo.
    echo Available backups:
    dir /b data\backups\*.sql 2>nul
    echo.
    set /p backup_file="Enter backup filename: "
    set backup_path=data\backups\%backup_file%
) else (
    set backup_path=%1
)

if not exist "%backup_path%" (
    echo ERROR: Backup file not found: %backup_path%
    pause
    exit /b 1
)

echo.
echo WARNING: This will overwrite the current database!
echo Backup file: %backup_path%
echo.
set /p confirm="Are you sure you want to continue? (yes/no): "

if /i not "%confirm%"=="yes" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Restoring database...

docker compose exec -T postgres psql -U tiktok_auto -d postgres -c "DROP DATABASE IF EXISTS tiktok_auto;"
docker compose exec -T postgres psql -U tiktok_auto -d postgres -c "CREATE DATABASE tiktok_auto;"
docker compose exec -T postgres psql -U tiktok_auto -d tiktok_auto < "%backup_path%"

if %errorlevel% equ 0 (
    echo.
    echo Database restored successfully!
) else (
    echo.
    echo Restore failed!
)

echo.
pause
