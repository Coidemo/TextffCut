@echo off
REM TextffCut Windows版ビルドスクリプト
REM PyInstallerでWindows実行ファイルを作成

echo =========================================
echo TextffCut Windows Build Script
echo =========================================
echo.

REM Pythonの確認
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8 or later
    pause
    exit /b 1
)

REM PyInstallerの確認
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM ビルドディレクトリをクリーンアップ
echo Cleaning build directories...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM PyInstallerでビルド
echo.
echo Building TextffCut CLI...
pyinstaller --onefile --name textffcut_cli_windows textffcut_cli_lite.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

REM ビルド成功
echo.
echo =========================================
echo Build completed successfully!
echo =========================================
echo.
echo Output file: dist\textffcut_cli_windows.exe
echo.

REM ファイルサイズを表示
echo File size:
dir dist\textffcut_cli_windows.exe | findstr /i exe
echo.

REM 動作テスト
echo Testing the build...
dist\textffcut_cli_windows.exe --version
echo.

echo Next steps:
echo 1. Test with actual video files
echo 2. Copy to release folder
echo 3. Create final package
echo.
pause