@echo off
chcp 65001 >nul 2>&1
set OLD_CODEPAGE=%errorlevel%
setlocal enabledelayedexpansion
title TextffCut Docker Manager

REM 色付き出力の代替（Windowsでは色なし）
echo ========================================
echo    TextffCut Docker Manager
echo ========================================
echo.

echo 🚀 TextffCut を起動しています...

REM ポートチェック関数の代替
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510
set FOUND=0

:find_port
netstat -an | findstr /r ":!PORT! .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    REM ポートが使用中
    if !PORT! neq !BASE_PORT! (
        echo ⚠️  ポート!BASE_PORT!が使用中のため、ポート!PORT!をチェック中...
    )
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

echo 📍 URL: http://localhost:!PORT!
echo.

REM Docker Desktopの確認
docker version >nul 2>&1
if errorlevel 1 (
    echo ❌ エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    pause
    exit /b 1
)

REM Docker Compose v2のチェック
docker compose version >nul 2>&1
if errorlevel 1 (
    REM v1を使用
    docker-compose up --build --remove-orphans
) else (
    REM v2を使用
    docker compose up --build --remove-orphans
)

REM クリーンアップ
if exist docker-compose.override.yml (
    del docker-compose.override.yml
)

REM 文字コードを元に戻す
if defined OLD_CODEPAGE chcp %OLD_CODEPAGE% >nul 2>&1
pause