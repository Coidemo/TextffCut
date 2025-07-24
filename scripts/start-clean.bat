@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title TextffCut Clean Start

echo ================================
echo    TextffCut Clean Start
echo ================================
echo.

REM スクリプトのディレクトリから一つ上に移動
cd /d "%~dp0.."

REM クリーンアップ
echo 🧹 既存のコンテナとイメージをクリーンアップしています...

REM TextffCutコンテナを停止・削除
for /f "tokens=*" %%i in ('docker ps -a --format "{{.Names}}" ^| findstr /i textffcut') do (
    echo    - コンテナを削除: %%i
    docker stop %%i >nul 2>&1
    docker rm %%i >nul 2>&1
)

REM docker-composeで管理されているコンテナを削除
if exist docker-compose.yml (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        docker-compose down -v >nul 2>&1
    ) else (
        docker compose down -v >nul 2>&1
    )
)

REM TextffCutイメージを削除
for /f "tokens=*" %%i in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr /i textffcut') do (
    echo    - イメージを削除: %%i
    docker rmi %%i >nul 2>&1
)

REM ボリュームを削除
for /f "tokens=*" %%i in ('docker volume ls --format "{{.Name}}" ^| findstr /i textffcut') do (
    echo    - ボリュームを削除: %%i
    docker volume rm %%i >nul 2>&1
)

echo ✓ クリーンアップ完了
echo.

REM Docker Desktop確認
docker version >nul 2>&1
if errorlevel 1 (
    echo ❌ エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    pause
    exit /b 1
)

REM ポートチェック
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510
set FOUND=0

:find_port
netstat -an | findstr /r ":!PORT! .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    REM ポートが使用中
    set /a PORT=PORT+1
    if !PORT! gtr !MAX_PORT! (
        echo ❌ エラー: 利用可能なポートが見つかりませんでした。
        pause
        exit /b 1
    )
    goto find_port
) else (
    REM ポートが空いている
    set FOUND=1
)

if !PORT! neq !BASE_PORT! (
    echo ⚠️  ポート!BASE_PORT!が使用中のため、ポート!PORT!を使用します。
    
    REM docker-compose.override.ymlを作成
    (
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
)

REM 必要なフォルダを作成
for %%f in (videos logs prompts) do (
    if not exist %%f (
        echo 📁 %%f フォルダを作成しています...
        mkdir %%f
    )
)

echo.
echo 🚀 クリーンビルドで起動しています...
echo 📍 URL: http://localhost:!PORT!
echo.

REM docker-composeで起動（--buildオプションで強制ビルド）
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose up --build --force-recreate --remove-orphans
) else (
    docker compose up --build --force-recreate --remove-orphans
)

REM クリーンアップ
if exist docker-compose.override.yml (
    del docker-compose.override.yml
)

pause