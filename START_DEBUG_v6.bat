@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 デバッグ版 v6
echo.

REM 現在のディレクトリを表示
echo 現在のディレクトリ:
cd
echo.

REM Docker確認
echo Docker確認中...
docker version >nul 2>&1
if errorlevel 1 (
    echo Docker Desktopが起動していません
    pause
    exit /b
)
echo Docker OK

REM Docker Compose確認（新版）
echo.
echo Docker Compose確認中...
docker compose version
if errorlevel 1 goto OLD_COMPOSE
echo docker compose を使用します
set COMPOSE_CMD=docker compose
goto COMPOSE_OK

:OLD_COMPOSE
echo 旧版を試します...
docker-compose version
if errorlevel 1 (
    echo Docker Composeが見つかりません
    pause
    exit /b
)
echo docker-compose を使用します
set COMPOSE_CMD=docker-compose

:COMPOSE_OK
echo.
echo 選択されたコマンド: %COMPOSE_CMD%
pause

REM ファイル確認
echo.
echo docker-compose-simple.yml確認中...
if not exist docker-compose-simple.yml (
    echo ファイルが見つかりません
    pause
    exit /b
)
echo ファイルOK

REM イメージ確認
echo.
echo Dockerイメージ確認中...
docker images | findstr textffcut
pause

REM 起動
echo.
echo 起動します...
%COMPOSE_CMD% -f docker-compose-simple.yml up

pause