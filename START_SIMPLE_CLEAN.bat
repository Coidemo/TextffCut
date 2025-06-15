@echo off
chcp 65001 >nul
echo Starting TextffCut v0.9.7 (Clean)...
echo.

REM Check Docker Desktop
docker version >nul 2>&1
if errorlevel 1 (
    echo Error: Docker Desktop is not running.
    echo Please start Docker Desktop and try again.
    pause
    exit /b
)

echo Cleaning up existing containers...
docker stop TextffCut 2>nul
docker rm TextffCut 2>nul
echo Cleanup complete.
echo.

echo Starting application...
docker-compose -f docker-compose-simple.yml up

pause