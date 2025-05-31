@echo off
REM TextffCut インストールスクリプト
REM Windows用

setlocal enabledelayedexpansion

echo.
echo ======================================
echo    TextffCut インストールスクリプト
echo ======================================
echo.

REM Python確認
echo 1. Python環境の確認...
python --version >nul 2>&1
if errorlevel 1 (
    echo エラー: Pythonがインストールされていません。
    echo Python 3.8以上をインストールしてください。
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo    Python %PYTHON_VERSION% が見つかりました。

REM FFmpeg確認
echo.
echo 2. FFmpegの確認...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo 警告: FFmpegがインストールされていません。
    echo.
    echo FFmpegをインストールするには:
    echo   1. https://ffmpeg.org/download.html からダウンロード
    echo   2. 任意の場所に解凍
    echo   3. システム環境変数のPATHに追加
    echo.
    set /p CONTINUE=続行しますか？ (y/n): 
    if /i not "!CONTINUE!"=="y" exit /b 1
) else (
    for /f "tokens=3" %%i in ('ffmpeg -version 2^>^&1 ^| findstr /i "version"') do set FFMPEG_VERSION=%%i
    echo    FFmpeg !FFMPEG_VERSION! が見つかりました。
)

REM 仮想環境の作成
echo.
echo 3. Python仮想環境の作成...
if exist venv (
    echo    既存の仮想環境が見つかりました。
    set /p RECREATE=   再作成しますか？ (y/n): 
    if /i "!RECREATE!"=="y" (
        rmdir /s /q venv
        python -m venv venv
        echo    仮想環境を再作成しました。
    )
) else (
    python -m venv venv
    echo    仮想環境を作成しました。
)

REM 仮想環境の有効化
echo.
echo 4. 仮想環境の有効化...
call venv\Scripts\activate.bat
echo    仮想環境を有効化しました。

REM pipのアップグレード
echo.
echo 5. pipのアップグレード...
python -m pip install --upgrade pip >nul 2>&1
echo    pipをアップグレードしました。

REM 依存関係のインストール
echo.
echo 6. 依存関係のインストール...
echo    これには数分かかる場合があります...

REM NVIDIA GPUの確認
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo    CPU版PyTorchをインストール中...
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
) else (
    echo    NVIDIA GPUが検出されました。CUDA版PyTorchをインストール中...
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
)

REM その他の依存関係
echo    その他の依存関係をインストール中...
pip install -r requirements.txt

REM インストール確認
echo.
echo 7. インストールの確認...
python -c "import streamlit; print('   OK: Streamlit')" 2>nul || echo    エラー: Streamlit
python -c "import torch; print('   OK: PyTorch')" 2>nul || echo    エラー: PyTorch
python -c "import whisperx; print('   OK: WhisperX')" 2>nul || echo    エラー: WhisperX
python -c "import openai; print('   OK: OpenAI')" 2>nul || echo    エラー: OpenAI

REM 起動スクリプトの作成
echo.
echo 8. 起動スクリプトの作成...
(
echo @echo off
echo REM TextffCut 起動スクリプト
echo.
echo REM スクリプトのディレクトリに移動
echo cd /d "%%~dp0"
echo.
echo REM 仮想環境の有効化
echo call venv\Scripts\activate.bat
echo.
echo REM アプリケーションの起動
echo streamlit run main.py
) > run.bat

echo    起動スクリプト 'run.bat' を作成しました。

REM 完了メッセージ
echo.
echo ======================================
echo    インストールが完了しました！
echo ======================================
echo.
echo TextffCutを起動するには:
echo   run.bat をダブルクリック
echo.
echo または、コマンドプロンプトで:
echo   run.bat
echo.
echo 手動で起動する場合:
echo   venv\Scripts\activate
echo   streamlit run main.py
echo.
echo APIモードを使用する場合は、起動後にサイドバーから
echo OpenAI APIキーを設定してください。
echo.
pause