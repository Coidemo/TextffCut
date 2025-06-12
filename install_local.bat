@echo off
echo =====================================
echo TextffCut ローカル版インストーラー
echo （Docker/WSL2不要）
echo =====================================
echo.

REM Python 3.11のチェック
python --version 2>nul | findstr "3.11" >nul
if errorlevel 1 (
    echo エラー: Python 3.11が見つかりません
    echo.
    echo Python 3.11をインストールしてください：
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM FFmpegのチェック
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo 警告: FFmpegが見つかりません
    echo.
    echo FFmpegをインストールすることを推奨します：
    echo https://ffmpeg.org/download.html
    echo.
    set /p continue=続行しますか？ (Y/N): 
    if /i not "%continue%"=="Y" exit /b 1
)

echo.
echo Python環境をセットアップ中...

REM 仮想環境の作成
if exist venv (
    echo 既存の仮想環境を削除中...
    rmdir /s /q venv
)

python -m venv venv
call venv\Scripts\activate.bat

REM pipのアップグレード
echo.
echo pipをアップグレード中...
python -m pip install --upgrade pip

REM 基本パッケージのインストール
echo.
echo 基本パッケージをインストール中...
pip install streamlit==1.37.0
pip install numpy==1.26.4
pip install pandas==2.0.3
pip install ffmpeg-python
pip install python-dotenv
pip install openai
pip install requests

echo.
echo =====================================
echo インストール完了！
echo.
echo 起動方法: start_local.bat
echo =====================================
echo.
pause