@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🚀 TextffCut を起動しています...

REM スクリプトのディレクトリから一つ上に移動
cd /d "%~dp0.."

REM 環境変数を設定
set HOST_VIDEOS_PATH=%cd%\videos

REM Docker Desktop確認
docker version >nul 2>&1
if errorlevel 1 (
    echo ❌ エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    pause
    exit /b 1
)

REM ポート8501を使用しているプロセスをチェック
set BASE_PORT=8501
set PORT=!BASE_PORT!
set PORT_IN_USE=0

netstat -an | findstr /r ":!PORT! .*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    set PORT_IN_USE=1
    echo ⚠️  警告: ポート!PORT!が既に使用されています。
    
    REM Dockerコンテナが使用しているかチェック
    set CONTAINER_FOUND=0
    for /f "tokens=*" %%i in ('docker ps --format "{{.Names}}"') do (
        docker port %%i 2>nul | findstr "!PORT!" >nul 2>&1
        if !errorlevel! equ 0 (
            set CONTAINER_FOUND=1
            set CONTAINER_NAME=%%i
            
            REM TextffCutのコンテナかチェック
            echo %%i | findstr /i "textffcut" >nul 2>&1
            if !errorlevel! equ 0 (
                echo 既存のTextffCutコンテナ(%%i)が起動しています。
                echo 自動的に停止して新しいコンテナを起動します...
                docker stop %%i >nul 2>&1
                docker rm %%i >nul 2>&1
                set PORT_IN_USE=0
            ) else (
                echo 別のDockerコンテナ(%%i)がポート!PORT!を使用しています。
            )
        )
    )
    
    if !PORT_IN_USE! equ 1 (
        if !CONTAINER_FOUND! equ 0 (
            echo Docker以外のプロセスがポート!PORT!を使用しています。
            
            REM プロセス情報を表示
            echo.
            echo 使用中のプロセス:
            for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":!PORT! .*LISTENING"') do (
                set PID=%%a
                for /f "skip=1 tokens=1 delims=," %%b in ('tasklist /fi "PID eq !PID!" /fo csv 2^>nul') do (
                    set PROCESS_NAME=%%~b
                    echo   PID: !PID! - !PROCESS_NAME!
                )
            )
            echo.
        )
        
        REM 別のポートを探す
        set FOUND=0
        for %%p in (8502 8503 8504 8505) do (
            if !FOUND! equ 0 (
                netstat -an | findstr ":%%p" | findstr "LISTENING" >nul 2>&1
                if !errorlevel! neq 0 (
                    set PORT=%%p
                    set FOUND=1
                    echo ✅ 代替ポート!PORT!を使用します。
                    set TEXTFFCUT_PORT=!PORT!
                )
            )
        )
        
        if !FOUND! equ 0 (
            echo ❌ エラー: 利用可能なポートが見つかりませんでした。
            echo 他のアプリケーションを終了してから再度お試しください。
            pause
            exit /b 1
        )
    )
)

REM 必要なフォルダを作成
for %%f in (videos logs prompts) do (
    if not exist %%f (
        echo 📁 %%f フォルダを作成しています...
        mkdir %%f
    )
)

echo.
echo ⏳ 起動を確認しています...
echo.

if defined TEXTFFCUT_PORT (
    REM docker-compose.override.ymlを作成
    (
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
    
    echo 📍 URL: http://localhost:!PORT!
    echo.
    
    REM docker-composeで起動
    docker compose version >nul 2>&1
    if errorlevel 1 (
        docker-compose up --build --remove-orphans
    ) else (
        docker compose up --build --remove-orphans
    )
    
    REM overrideファイルを削除
    del docker-compose.override.yml
) else (
    echo 📍 URL: http://localhost:8501
    echo.
    
    REM 通常のポートで起動
    docker compose version >nul 2>&1
    if errorlevel 1 (
        docker-compose up --build --remove-orphans
    ) else (
        docker compose up --build --remove-orphans
    )
)

echo.
echo ✅ TextffCut を終了しました。
pause