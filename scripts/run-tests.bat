@echo off
REM TikTok Auto - Run Tests
REM Usage: Double-click to run all tests

cd /d "%~dp0.."

echo TikTok Auto - Test Runner
echo ==========================
echo.

REM Check if venv exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -q -r requirements-dev.txt
pip install -q -e shared\python

REM Install service dependencies
for /d %%s in (services\*) do (
    if exist "%%s\requirements.txt" (
        pip install -q -r "%%s\requirements.txt" 2>nul
    )
)

echo.
echo Running tests...
echo.

pytest --cov=shared --cov=services --cov-report=term-missing

echo.
if %errorlevel% equ 0 (
    echo All tests passed!
) else (
    echo Some tests failed.
)

echo.
pause
