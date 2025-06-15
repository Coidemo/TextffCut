@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 デバッグ版 v5
echo.

REM エラーが発生しても続行
setlocal enabledelayedexpansion

REM 現在のディレクトリを表示
echo [0] 現在のディレクトリ:
cd
echo.

REM 環境変数を設定
set HOST_VIDEOS_PATH=%cd%\videos

echo [1] Docker確認中...
docker version >nul 2>&1
if !errorlevel! neq 0 (
    echo X Docker Desktopが起動していません
    echo エラーコード: !errorlevel!
    pause
    exit /b 1
)
echo OK Docker Desktop: OK

echo.
echo [2] Docker Compose確認中...
docker compose version 2>&1
if !errorlevel! neq 0 (
    echo 旧版を試します...
    docker-compose version 2>&1
    if !errorlevel! neq 0 (
        echo X Docker Composeが見つかりません
        pause
        exit /b 1
    )
    set COMPOSE_CMD=docker-compose
) else (
    set COMPOSE_CMD=docker compose
)
echo 使用するコマンド: %COMPOSE_CMD%

echo.
echo [3] フォルダ作成をスキップ（問題の原因の可能性）

echo.
echo [4] docker-compose-simple.yml確認中...
if exist docker-compose-simple.yml (
    echo OK ファイル存在
) else (
    echo X ファイルなし
    pause
    exit /b 1
)

echo.
echo [5] イメージ確認中...
docker images 2>&1 | findstr /C:"textffcut" | findstr /C:"0.9.7"
if !errorlevel! neq 0 (
    echo イメージをロードします...
    if exist textffcut_v0.9.7_docker.tar.gz (
        docker load -i textffcut_v0.9.7_docker.tar.gz
    ) else (
        echo X tar.gzファイルなし
        pause
        exit /b 1
    )
)

echo.
echo ここまで到達
pause

echo.
echo [6] 起動します...
%COMPOSE_CMD% -f docker-compose-simple.yml up

pause