@echo off
echo ========================================
echo TextffCut - WSL2セットアップ
echo ========================================
echo.

REM 管理者権限チェック
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo エラー: 管理者権限で実行してください。
    echo 右クリック → 「管理者として実行」を選択してください。
    pause
    exit /b 1
)

echo WSL2のセットアップを開始します...
echo.

REM 必要な機能を有効化
echo [1/4] Windows機能を有効化しています...
powershell -Command "Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart -All | Out-Null"
powershell -Command "Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart -All | Out-Null"

REM WSL2をインストール
echo [2/4] WSL2をインストールしています...
wsl --install --no-distribution

REM WSL2をデフォルトに設定
echo [3/4] WSL2を設定しています...
wsl --set-default-version 2

echo.
echo [4/4] セットアップが完了しました！
echo.
echo ========================================
echo 重要: システムを再起動してください
echo ========================================
echo.
echo 再起動後、Docker Desktopが正常に動作するようになります。
echo.
pause