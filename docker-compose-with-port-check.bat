@echo off
REM 文字コードをUTF-8に設定（元の設定を保存）
for /f "tokens=2 delims=:" %%a in ('chcp') do set ORIGINAL_CP=%%a
chcp 65001 >nul
setlocal enabledelayedexpansion

REM タイトル設定
title TextffCut Docker Manager

echo ========================================
echo    TextffCut Docker Manager
echo ========================================
echo.

echo 🚀 TextffCut を起動しています...

REM Docker Desktopの確認
docker version >nul 2>&1
if errorlevel 1 (
    echo ❌ エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    goto :cleanup
)

REM ポート設定
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510
set FOUND=0

REM 利用可能なポートを探す
:find_port
    REM IPv4とIPv6両方をチェック（正規表現で完全一致）
    netstat -an | findstr /r ":\<!PORT!\>" | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        REM ポートが使用中
        if !PORT! neq !BASE_PORT! (
            echo ⚠️  ポート!PORT!が使用中です...
        )
        set /a PORT=PORT+1
        if !PORT! gtr !MAX_PORT! (
            echo ❌ エラー: 利用可能なポートが見つかりませんでした（!BASE_PORT!-!MAX_PORT!）。
            goto :cleanup
        )
        goto find_port
    )

REM ポートが決定
if !PORT! neq !BASE_PORT! (
    echo ⚠️  ポート!BASE_PORT!が使用中のため、ポート!PORT!を使用します。
    
    REM docker-compose.override.ymlを作成（適切なインデント）
    (
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
)

echo 📍 URL: http://localhost:!PORT!
echo.
echo 📝 Ctrl+C で終了できます。
echo.

REM Docker Compose起動（v2優先）
docker compose version >nul 2>&1
if errorlevel 1 (
    REM v1を使用
    docker-compose up --build
) else (
    REM v2を使用
    docker compose up --build
)

:cleanup
REM overrideファイルのクリーンアップ
if exist docker-compose.override.yml (
    del /q docker-compose.override.yml >nul 2>&1
)

REM 文字コードを元に戻す
chcp %ORIGINAL_CP% >nul

pause
exit /b