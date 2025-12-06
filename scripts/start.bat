@echo off
REM TikTok Auto - Start Services
REM Usage: Double-click or run from command prompt

cd /d "%~dp0.."

echo Starting TikTok Auto...
echo.

REM Check for .env file
if not exist .env (
    echo Warning: .env file not found. Creating from template...
    copy .env.example .env
    echo Please edit .env with your credentials before continuing.
    pause
    exit /b 1
)

REM Create data directories
if not exist data\backgrounds mkdir data\backgrounds
if not exist data\audio mkdir data\audio
if not exist data\videos mkdir data\videos
if not exist data\scripts mkdir data\scripts
if not exist data\logs mkdir data\logs
if not exist data\backups mkdir data\backups

REM Start all services
echo Starting all services...
docker compose up -d

echo.
echo Services started!
echo.
echo Dashboard:    http://localhost:8080
echo Uploader:     http://localhost:3000
echo Grafana:      http://localhost:3001
echo Prometheus:   http://localhost:9090
echo.
pause
