@echo off
REM TikTok Auto - Initial Setup
REM Run this script to set up the development environment

cd /d "%~dp0.."

echo ===========================
echo TikTok Auto Setup
echo ===========================
echo.

REM Check Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker is not installed. Please install Docker Desktop first.
    pause
    exit /b 1
)

echo [OK] Docker is installed

REM Check Docker Compose
docker compose version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker Compose is not available.
    pause
    exit /b 1
)

echo [OK] Docker Compose is available
echo.

REM Create .env file if not exists
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Please edit .env file with your credentials:
    echo   - REDDIT_CLIENT_ID
    echo   - REDDIT_SECRET
    echo.
    notepad .env
)

REM Create data directories
echo Creating data directories...
if not exist data\backgrounds mkdir data\backgrounds
if not exist data\audio mkdir data\audio
if not exist data\videos mkdir data\videos
if not exist data\scripts mkdir data\scripts
if not exist data\logs mkdir data\logs
if not exist data\backups mkdir data\backups
echo [OK] Data directories created
echo.

REM Build Docker images
echo Building Docker images (this may take a few minutes)...
docker compose build

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Docker build failed!
    pause
    exit /b 1
)

echo.
echo [OK] Docker images built
echo.

REM Start infrastructure
echo Starting infrastructure services...
docker compose up -d postgres redis elasticsearch ollama piper

echo.
echo Waiting for services to be ready (30 seconds)...
timeout /t 30 /nobreak >nul

echo.
echo ===========================
echo Setup Complete!
echo ===========================
echo.
echo Next steps:
echo 1. Add background videos to data\backgrounds\
echo 2. Run start.bat to start all services
echo 3. Open http://localhost:8080 for the dashboard
echo 4. Run open-tiktok-login.bat to authenticate with TikTok
echo.
pause
