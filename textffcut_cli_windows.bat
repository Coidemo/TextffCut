@echo off
REM TextffCut CLI Lite - Windows起動スクリプト

echo ========================================
echo TextffCut CLI Lite - Windows版
echo ========================================
echo.

REM ffmpegの存在確認
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] ffmpegが見つかりません。
    echo.
    echo ffmpegをインストールしてください：
    echo https://ffmpeg.org/download.html
    echo.
    echo または、Chocolateyを使用：
    echo choco install ffmpeg
    echo.
    pause
    exit /b 1
)

REM 引数がない場合はヘルプを表示
if "%~1"=="" (
    textffcut_cli_lite.exe --help
    echo.
    pause
    exit /b 0
)

REM コマンドを実行
textffcut_cli_lite.exe %*

REM エラーレベルを確認
if %errorlevel% neq 0 (
    echo.
    echo [エラー] 処理が失敗しました。
    pause
)