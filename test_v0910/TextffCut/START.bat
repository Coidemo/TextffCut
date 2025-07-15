@echo off
chcp 65001 >nul
echo Starting TextffCut v0.9.10...
echo.

echo Checking Docker...
docker version >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop not running
    echo Please start Docker Desktop and try again.
    pause
    exit /b
)
echo Docker OK
echo.

echo Checking Docker Compose v2...
docker compose version >nul 2>&1
if errorlevel 1 (
    echo Docker Compose v2 not found. Using v1...
    set COMPOSE_CMD=docker-compose
) else (
    echo Docker Compose v2 OK
    set COMPOSE_CMD=docker compose
)
echo.

echo Creating folders...
for %%f in (videos logs models prompts) do (
    if not exist %%f (
        mkdir %%f
        echo Created %%f folder
    )
)
echo.

echo Loading Docker image...
docker images | findstr textffcut:0.9.10 >nul 2>&1
if errorlevel 1 (
    echo Loading image (first time only)...
    docker load -i textffcut_v0.9.10_docker.tar.gz
) else (
    echo Image already loaded
)
echo.

echo Starting TextffCut...
echo URL: http://localhost:8501
echo Videos folder: %cd%\videos
echo.
echo Opening browser...
start http://localhost:8501

%COMPOSE_CMD% -f docker-compose-simple.yml up

pause
