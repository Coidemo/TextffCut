@echo off
echo TextffCut ローカル版を起動中...
echo.

REM 仮想環境の有効化
if not exist venv (
    echo エラー: 仮想環境が見つかりません
    echo install_local.bat を実行してください
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM アプリケーションの起動
echo ブラウザで http://localhost:8501 を開いてください
echo.
echo 終了するには Ctrl+C を押してください
echo.

streamlit run main.py

pause