@echo off
REM 文字コードをUTF-8に設定
for /f "tokens=2 delims=:" %%a in ('chcp') do set ORIGINAL_CP=%%a
chcp 65001 >nul
setlocal enabledelayedexpansion

title TextffCut Development

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
    goto :cleanup
)

REM ポート設定
set BASE_PORT=8501
set PORT=!BASE_PORT!
set PORT_IN_USE=0
set TEXTFFCUT_PORT=

REM ポート使用状況をチェック
netstat -an | findstr /r ":\<!PORT!\>" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    set PORT_IN_USE=1
    echo ⚠️  警告: ポート!PORT!が既に使用されています。
    
    REM Dockerコンテナが使用しているかチェック（簡略化）
    set TEXTFFCUT_CONTAINER=
    for /f "tokens=*" %%i in ('docker ps --filter "name=textffcut" --format "{{.Names}}"') do (
        set TEXTFFCUT_CONTAINER=%%i
    )
    
    if defined TEXTFFCUT_CONTAINER (
        echo 既存のTextffCutコンテナ(!TEXTFFCUT_CONTAINER!)が起動しています。
        echo 自動的に停止して新しいコンテナを起動します...
        docker stop !TEXTFFCUT_CONTAINER! >nul 2>&1
        timeout /t 2 /nobreak >nul
        set PORT_IN_USE=0
    ) else (
        REM 別のプロセスが使用中 - プロセス情報を表示
        echo.
        echo 使用中のプロセス:
        for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":\<!PORT!\>" ^| findstr "LISTENING"') do (
            set PID=%%a
            REM tasklist出力をより安全に処理
            for /f "skip=1 tokens=1" %%b in ('tasklist /fi "PID eq !PID!" /fo csv 2^>nul') do (
                set PROCESS_NAME=%%b
                echo   PID: !PID! - !PROCESS_NAME:"=!
            )
        )
        echo.
        
        REM 代替ポートを探す
        for /l %%p in (8502,1,8510) do (
            if not defined TEXTFFCUT_PORT (
                netstat -an | findstr /r ":\<%%p\>" | findstr "LISTENING" >nul 2>&1
                if errorlevel 1 (
                    set PORT=%%p
                    set TEXTFFCUT_PORT=%%p
                    echo ✅ 代替ポート!PORT!を使用します。
                )
            )
        )
        
        if not defined TEXTFFCUT_PORT (
            echo ❌ エラー: 利用可能なポートが見つかりませんでした。
            echo 他のアプリケーションを終了してから再度お試しください。
            goto :cleanup
        )
    )
)

REM 必要なフォルダを作成
for %%f in (videos logs prompts) do (
    if not exist %%f (
        echo 📁 %%f フォルダを作成しています...
        mkdir %%f 2>nul
    )
)

echo.
echo ⏳ 起動準備中...
echo.

REM ポート設定が必要な場合
if defined TEXTFFCUT_PORT (
    REM docker-compose.override.ymlを作成
    (
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
)

echo 📍 URL: http://localhost:!PORT!
echo 📝 Ctrl+C で終了できます。
echo.

REM Docker Compose起動
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose up --build
) else (
    docker compose up --build
)

:cleanup
REM overrideファイルを削除
if exist docker-compose.override.yml (
    del /q docker-compose.override.yml >nul 2>&1
)

REM 文字コードを元に戻す
chcp %ORIGINAL_CP% >nul

echo.
echo ✅ TextffCut を終了しました。
pause
exit /b