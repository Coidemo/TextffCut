@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 Debug v7
echo.

echo Current directory:
cd
echo.

echo Checking Docker...
docker version >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop not running
    pause
    exit /b
)
echo Docker OK

echo.
echo Checking Docker Compose...
docker compose version
if errorlevel 1 goto OLD_COMPOSE
echo Using docker compose
set COMPOSE_CMD=docker compose
goto COMPOSE_OK

:OLD_COMPOSE
echo Trying old version...
docker-compose version
if errorlevel 1 (
    echo Docker Compose not found
    pause
    exit /b
)
echo Using docker-compose
set COMPOSE_CMD=docker-compose

:COMPOSE_OK
echo.
echo Selected command: %COMPOSE_CMD%
pause

echo.
echo Checking docker-compose-simple.yml...
if not exist docker-compose-simple.yml (
    echo File not found
    pause
    exit /b
)
echo File OK

echo.
echo Checking Docker image...
docker images | findstr textffcut
pause

echo.
echo Starting...
%COMPOSE_CMD% -f docker-compose-simple.yml up

pause