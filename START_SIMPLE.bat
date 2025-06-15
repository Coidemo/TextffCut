@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 簡易起動スクリプト
echo.

REM Dockerイメージをロード
echo Dockerイメージを読み込み中...
docker load -i textffcut_v0.9.7_docker.tar.gz

echo.
echo 起動中...
docker run -d --name TextffCut -p 8501:8501 -v "%cd%\videos:/app/videos" -v "%cd%\logs:/app/logs" -v "%cd%\models:/home/appuser/.cache" textffcut:0.9.7

echo.
echo TextffCutが起動しました
echo ブラウザで http://localhost:8501 を開いてください
echo.
pause