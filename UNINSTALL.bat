@echo off
title TextffCut アンインストール

echo 🗑️  TextffCut のアンインストール
echo ================================
echo.
echo 以下を削除します：
echo 1. Dockerコンテナ
echo 2. Dockerイメージ（約4GB）
echo 3. このフォルダ内の作業データ
echo.
echo ⚠️  注意: videosフォルダ内の動画は削除されません
echo.
set /p CONFIRM="続行しますか？ (y/N): "

if /i "%CONFIRM%"=="y" (
    echo.
    echo 🧹 クリーンアップ中...
    
    REM コンテナを停止・削除
    echo - コンテナを削除...
    docker-compose -f docker-compose-simple.yml down 2>nul
    
    REM イメージを削除
    echo - Dockerイメージを削除...
    docker rmi textffcut:1.1.0 2>nul
    
    REM 作業ファイルを削除（videosは除く）
    echo - 作業ファイルを削除...
    if exist output\* del /q output\*
    if exist transcriptions\* del /q transcriptions\*
    if exist logs\* del /q logs\*
    
    echo.
    echo ✅ アンインストール完了！
    echo.
    echo このフォルダ自体を削除するには：
    echo 1. このウィンドウを閉じる
    echo 2. TextffCut-Docker-Complete フォルダをゴミ箱に入れる
) else (
    echo.
    echo ❌ アンインストールをキャンセルしました
)

echo.
pause