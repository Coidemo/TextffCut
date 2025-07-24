@echo off
REM 文字コードをUTF-8に設定
for /f "tokens=2 delims=:" %%a in ('chcp') do set ORIGINAL_CP=%%a
chcp 65001 >nul
setlocal enabledelayedexpansion

title TextffCut Clean Start

echo ================================
echo    TextffCut Clean Start
echo ================================
echo.

REM スクリプトのディレクトリから一つ上に移動
cd /d "%~dp0.."

REM ユーザー確認
echo ⚠️  警告: この操作により以下が削除されます：
echo    - TextffCut関連のすべてのDockerコンテナ
echo    - TextffCut関連のすべてのDockerイメージ
echo    - TextffCut関連のすべてのDockerボリューム
echo.
set /p CONFIRM="続行しますか？ (y/N): "
if /i not "!CONFIRM!"=="y" (
    echo 操作をキャンセルしました。
    goto :cleanup
)

echo.
echo 🧹 既存のコンテナとイメージをクリーンアップしています...

REM Docker Compose管理のリソースを削除
if exist docker-compose.yml (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        docker-compose down -v --remove-orphans >nul 2>&1
    ) else (
        docker compose down -v --remove-orphans >nul 2>&1
    )
)

REM TextffCutコンテナを停止・削除（より正確なフィルタ）
for /f "tokens=*" %%i in ('docker ps -a --filter "name=textffcut" --format "{{.Names}}"') do (
    echo    - コンテナを削除: %%i
    docker stop %%i >nul 2>&1
    docker rm -f %%i >nul 2>&1
)

REM TextffCutイメージを削除（より正確なフィルタ）
for /f "tokens=1,2" %%a in ('docker images --format "table {{.Repository}}:{{.Tag}}" ^| findstr /i "textffcut"') do (
    echo    - イメージを削除: %%a
    docker rmi -f %%a >nul 2>&1
)

REM ボリュームを削除（より安全なフィルタ）
for /f "tokens=*" %%i in ('docker volume ls --filter "name=textffcut" --format "{{.Name}}"') do (
    echo    - ボリュームを削除: %%i
    docker volume rm -f %%i >nul 2>&1
)

REM ビルドキャッシュをクリア
echo    - ビルドキャッシュをクリア中...
docker builder prune -f >nul 2>&1

echo ✓ クリーンアップ完了
echo.

REM ポートチェック
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510

:find_port
    netstat -an | findstr /r ":\<!PORT!\>" | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        set /a PORT=PORT+1
        if !PORT! gtr !MAX_PORT! (
            echo ❌ エラー: 利用可能なポートが見つかりませんでした。
            goto :cleanup
        )
        goto find_port
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
        mkdir %%f 2>nul
    )
)

echo.
echo 🚀 クリーンビルドで起動しています...
echo 📍 URL: http://localhost:!PORT!
echo 📝 Ctrl+C で終了できます。
echo.

REM Docker Compose起動（キャッシュなしでビルド）
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose build --no-cache
    docker-compose up --force-recreate
) else (
    docker compose build --no-cache
    docker compose up --force-recreate
)

:cleanup
REM overrideファイルを削除
if exist docker-compose.override.yml (
    del /q docker-compose.override.yml >nul 2>&1
)

REM 文字コードを元に戻す
chcp %ORIGINAL_CP% >nul

pause
exit /b