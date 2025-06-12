@echo off
echo Starting TextffCut for Windows...
echo.

REM 必要なフォルダを作成
if not exist "videos" mkdir videos
if not exist "output" mkdir output
if not exist "transcriptions" mkdir transcriptions
if not exist "logs" mkdir logs
if not exist "models" mkdir models
if not exist "optimizer_profiles" mkdir optimizer_profiles

REM Docker Desktopが起動しているか確認
docker version >nul 2>&1
if errorlevel 1 (
    echo Error: Docker Desktop is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

REM 既存のコンテナを停止
echo Stopping existing container...
docker-compose -f docker-compose.windows.yml down

REM コンテナを起動
echo Starting container...
docker-compose -f docker-compose.windows.yml up -d

REM 起動確認
timeout /t 5 /nobreak >nul
docker ps | findstr textffcut_app >nul
if errorlevel 1 (
    echo Error: Container failed to start!
    echo Check logs with: docker logs textffcut_app
    pause
    exit /b 1
)

echo.
echo TextffCut is running!
echo Access at: http://localhost:8501
echo.
echo To view logs: docker logs -f textffcut_app
echo To stop: docker-compose -f docker-compose.windows.yml down
echo.
pause