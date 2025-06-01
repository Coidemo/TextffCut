@echo off
title TextffCut 起動

echo 📁 作業フォルダ: %cd%
echo    動画は: %cd%\videos に入れてください
echo    結果は: %cd%\output に出力されます
echo.
echo 🚀 TextffCut を起動しています...
echo.
echo 初回起動時はDockerイメージの読み込みに時間がかかります。
echo.

REM Dockerイメージの確認
docker images textffcut:1.1.0 >nul 2>&1
if errorlevel 1 (
    if exist textffcut-1.1.0-docker.tar.gz (
        echo 📦 Dockerイメージを読み込んでいます...
        docker load -i textffcut-1.1.0-docker.tar.gz
    )
)

REM 既存のコンテナをチェックして削除
docker ps -a | findstr textffcut_app >nul 2>&1
if %errorlevel%==0 (
    echo ⚠️  既に起動中または停止中のコンテナがあります
    echo    既存のコンテナを削除して再起動します...
    docker stop textffcut_app 2>nul
    docker rm textffcut_app 2>nul
)

REM Docker Composeで起動（現在のディレクトリを環境変数として渡す）
echo 🌐 起動中...
echo.
echo ブラウザで以下のURLを開いてください：
echo 👉 http://localhost:8501
echo.
echo （終了するには Ctrl+C を押してください）
echo.
set HOST_VIDEOS_PATH=%cd%\videos
docker-compose -f docker-compose-simple.yml up

echo.
echo 終了しました。Enterキーを押してください。
pause >nul