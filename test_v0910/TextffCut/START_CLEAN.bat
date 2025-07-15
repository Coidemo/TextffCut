@echo off
chcp 65001 >nul
echo TextffCut v0.9.10 Clean Start
echo.

echo Cleaning up existing containers and images...
echo.

REM Stop and remove TextffCut containers
echo Stopping containers...
for /f "tokens=*" %%i in ('docker ps -a --format "{{.Names}}" ^| findstr /i textffcut') do (
    echo - Stopping %%i
    docker stop %%i >nul 2>&1
    docker rm %%i >nul 2>&1
)

REM Check for Docker Compose v2
docker compose version >nul 2>&1
if errorlevel 1 (
    set COMPOSE_CMD=docker-compose
) else (
    set COMPOSE_CMD=docker compose
)

REM Clean up with docker-compose
if exist docker-compose-simple.yml (
    %COMPOSE_CMD% -f docker-compose-simple.yml down >nul 2>&1
)

REM Remove all textffcut images
echo.
echo Removing all images...
for /f "tokens=*" %%i in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr /i textffcut') do (
    echo - Removing %%i
    docker rmi %%i >nul 2>&1
)

REM Remove volumes
echo.
echo Removing volumes...
for /f "tokens=*" %%i in ('docker volume ls --format "{{.Name}}" ^| findstr /i textffcut') do (
    echo - Removing %%i
    docker volume rm %%i >nul 2>&1
)

echo.
echo Cleanup complete!
echo.

REM Check Docker
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

REM Create folders
echo Creating folders...
for %%f in (videos logs models prompts) do (
    if not exist %%f (
        mkdir %%f
        echo Created %%f folder
    )
)
echo.

REM Load fresh image
echo Loading Docker image...
docker load -i textffcut_v0.9.10_docker.tar.gz
echo.

echo Starting TextffCut...
echo URL: http://localhost:8501
echo Videos folder: %cd%\videos
echo.
echo Opening browser...
start http://localhost:8501

%COMPOSE_CMD% -f docker-compose-simple.yml up

pause
