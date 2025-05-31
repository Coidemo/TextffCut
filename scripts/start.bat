@echo off
echo 🎬 TextffCut を起動します...

REM 必要なフォルダを自動作成
if not exist "videos" (
    echo 📁 videos フォルダを作成しています...
    mkdir videos
)

if not exist "transcriptions" (
    echo 📁 transcriptions フォルダを作成しています...
    mkdir transcriptions
)

echo 🚀 TextffCut を起動中...
echo 📍 ブラウザで http://localhost:8501 を開いてください
echo.
echo 停止するには Ctrl+C を押してください
echo.

REM Dockerコンテナを起動
docker run -p 8501:8501 ^
  -v "%cd%\videos:/app/videos" ^
  -v "%cd%\transcriptions:/app/transcriptions" ^
  textffcut:latest