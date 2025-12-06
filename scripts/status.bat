@echo off
REM TikTok Auto - Check Service Status
REM Usage: Double-click or run from command prompt

cd /d "%~dp0.."

echo TikTok Auto - Service Status
echo ==============================
echo.

echo Docker Services:
docker compose ps
echo.

echo Health Checks:

REM Dashboard
curl -s http://localhost:8080/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   Dashboard:    healthy
) else (
    echo   Dashboard:    unhealthy
)

REM Uploader
curl -s http://localhost:3000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   Uploader:     healthy
) else (
    echo   Uploader:     unhealthy
)

REM Prometheus
curl -s http://localhost:9090/-/healthy >nul 2>&1
if %errorlevel% equ 0 (
    echo   Prometheus:   healthy
) else (
    echo   Prometheus:   unhealthy
)

REM Grafana
curl -s http://localhost:3001/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   Grafana:      healthy
) else (
    echo   Grafana:      unhealthy
)

echo.
echo Database Stats:
docker compose exec -T postgres psql -U tiktok_auto -d tiktok_auto -c "SELECT (SELECT COUNT(*) FROM stories WHERE status = 'pending') as pending, (SELECT COUNT(*) FROM stories WHERE status = 'approved') as approved, (SELECT COUNT(*) FROM stories WHERE status = 'processing') as processing, (SELECT COUNT(*) FROM stories WHERE status = 'completed') as completed, (SELECT COUNT(*) FROM stories WHERE status = 'failed') as failed;" 2>nul

echo.
echo Dashboard: http://localhost:8080
echo Grafana:   http://localhost:3001
echo.
pause
