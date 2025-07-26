@echo off
REM 共通関数ライブラリ

REM ポート検出関数
:check_port
    set PORT_TO_CHECK=%1
    set PORT_AVAILABLE=1
    
    REM IPv4とIPv6両方をチェック
    netstat -an | findstr /r ":\<%PORT_TO_CHECK%\>" | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        set PORT_AVAILABLE=0
    )
    exit /b %PORT_AVAILABLE%

REM Docker状態確認
:check_docker
    docker version >nul 2>&1
    if errorlevel 1 (
        echo ❌ エラー: Docker Desktopが起動していません。
        echo Docker Desktopを起動してから、もう一度実行してください。
        pause
        exit /b 1
    )
    exit /b 0

REM YAMLファイル作成関数
:create_override_yaml
    set OVERRIDE_PORT=%1
    (
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "%OVERRIDE_PORT%:8501"
    ) > docker-compose.override.yml
    exit /b 0

REM クリーンアップ関数
:cleanup_override
    if exist docker-compose.override.yml (
        del /q docker-compose.override.yml >nul 2>&1
    )
    exit /b 0