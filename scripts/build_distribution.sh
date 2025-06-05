#!/bin/bash
#
# TextffCut 配布パッケージ作成スクリプト
# Docker imageを作成し、配布用のファイルをパッケージ化します
#

set -e

# バージョンを取得
VERSION=${1:-$(cat VERSION.txt 2>/dev/null || echo "1.0.0")}
RELEASE_NAME="TextffCut_v${VERSION}"
RELEASE_DIR="release/${RELEASE_NAME}"

echo "=========================================="
echo "TextffCut 配布パッケージ作成"
echo "バージョン: ${VERSION}"
echo "=========================================="

# 作業ディレクトリを作成
echo "1. 作業ディレクトリを準備..."
rm -rf "${RELEASE_DIR}"
mkdir -p "${RELEASE_DIR}"

# Dockerイメージをビルド
echo "2. Dockerイメージをビルド..."
docker build -t textffcut:latest -t textffcut:${VERSION} .

# Dockerイメージを保存
echo "3. Dockerイメージを保存..."
docker save textffcut:${VERSION} | gzip > "${RELEASE_DIR}/textffcut_${VERSION}.tar.gz"

# 起動スクリプトを作成（Mac/Linux用）
echo "4. 起動スクリプトを作成..."
cat > "${RELEASE_DIR}/START_GUI.sh" << 'EOF'
#!/bin/bash
#
# TextffCut 起動スクリプト (Mac/Linux)
#

echo "TextffCut を起動しています..."

# Dockerが起動していることを確認
if ! docker info > /dev/null 2>&1; then
    echo "エラー: Docker Desktopが起動していません。"
    echo "Docker Desktopを起動してから、このスクリプトを再実行してください。"
    exit 1
fi

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# Dockerイメージが読み込まれているか確認
if ! docker images | grep -q "textffcut"; then
    echo "Dockerイメージを読み込んでいます..."
    docker load < textffcut_*.tar.gz
fi

# 必要なディレクトリを作成
mkdir -p videos videos/output transcriptions logs

# コンテナを起動
echo "コンテナを起動しています..."
docker run -d \
    --name textffcut \
    -p 8501:8501 \
    -v "$(pwd)/videos:/app/videos" \
    -v "$(pwd)/videos/output:/app/output" \
    -v "$(pwd)/transcriptions:/app/transcriptions" \
    -v "$(pwd)/logs:/app/logs" \
    -e TEXTFFCUT_ISOLATION_MODE=subprocess \
    --restart unless-stopped \
    textffcut:latest

# 起動を待つ
echo "アプリケーションの起動を待っています..."
sleep 5

# ブラウザを開く
if command -v open > /dev/null 2>&1; then
    open http://localhost:8501
elif command -v xdg-open > /dev/null 2>&1; then
    xdg-open http://localhost:8501
fi

echo ""
echo "=========================================="
echo "TextffCut が起動しました！"
echo "ブラウザで http://localhost:8501 を開いてください。"
echo ""
echo "停止するには: docker stop textffcut"
echo "再起動するには: docker start textffcut"
echo "=========================================="
EOF

# 起動スクリプトを作成（Windows用）
cat > "${RELEASE_DIR}/START_GUI.bat" << 'EOF'
@echo off
REM TextffCut 起動スクリプト (Windows)

echo TextffCut を起動しています...

REM Dockerが起動していることを確認
docker info >nul 2>&1
if errorlevel 1 (
    echo エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、このスクリプトを再実行してください。
    pause
    exit /b 1
)

REM スクリプトのディレクトリに移動
cd /d %~dp0

REM Dockerイメージが読み込まれているか確認
docker images | findstr textffcut >nul 2>&1
if errorlevel 1 (
    echo Dockerイメージを読み込んでいます...
    for %%f in (textffcut_*.tar.gz) do (
        docker load < %%f
    )
)

REM 必要なディレクトリを作成
if not exist videos mkdir videos
if not exist videos\output mkdir videos\output
if not exist transcriptions mkdir transcriptions
if not exist logs mkdir logs

REM コンテナを起動
echo コンテナを起動しています...
docker run -d ^
    --name textffcut ^
    -p 8501:8501 ^
    -v "%cd%\videos:/app/videos" ^
    -v "%cd%\videos\output:/app/output" ^
    -v "%cd%\transcriptions:/app/transcriptions" ^
    -v "%cd%\logs:/app/logs" ^
    -e TEXTFFCUT_ISOLATION_MODE=subprocess ^
    --restart unless-stopped ^
    textffcut:latest

REM 起動を待つ
echo アプリケーションの起動を待っています...
timeout /t 5 >nul

REM ブラウザを開く
start http://localhost:8501

echo.
echo ==========================================
echo TextffCut が起動しました！
echo ブラウザで http://localhost:8501 を開いてください。
echo.
echo 停止するには: docker stop textffcut
echo 再起動するには: docker start textffcut
echo ==========================================
pause
EOF

# 停止スクリプトを作成
cat > "${RELEASE_DIR}/STOP.sh" << 'EOF'
#!/bin/bash
docker stop textffcut
docker rm textffcut
echo "TextffCut を停止しました。"
EOF

cat > "${RELEASE_DIR}/STOP.bat" << 'EOF'
@echo off
docker stop textffcut
docker rm textffcut
echo TextffCut を停止しました。
pause
EOF

# READMEを作成
cat > "${RELEASE_DIR}/README.txt" << EOF
TextffCut v${VERSION}
===================

動画の文字起こしと切り抜きを効率化するツール

【必要なソフトウェア】
- Docker Desktop

【使い方】
1. Docker Desktopを起動します
2. START_GUI.sh (Mac/Linux) または START_GUI.bat (Windows) を実行します
3. ブラウザで http://localhost:8501 が開きます
4. videosフォルダに動画ファイルを入れて使用してください

【フォルダ構成】
- videos/       : 動画ファイルを入れるフォルダ
- videos/output/: 処理済みファイルが出力されるフォルダ
- transcriptions/: 文字起こし結果の保存フォルダ
- logs/         : ログファイルの保存フォルダ

【停止方法】
STOP.sh (Mac/Linux) または STOP.bat (Windows) を実行してください

【サポート】
https://github.com/your-repo/textffcut
EOF

# 実行権限を付与
chmod +x "${RELEASE_DIR}/START_GUI.sh"
chmod +x "${RELEASE_DIR}/STOP.sh"

# ZIPファイルを作成
echo "5. ZIPファイルを作成..."
cd release
zip -r "${RELEASE_NAME}.zip" "${RELEASE_NAME}"
cd ..

# ファイルサイズを表示
SIZE=$(du -h "${RELEASE_DIR}.zip" | cut -f1)

echo ""
echo "=========================================="
echo "配布パッケージの作成が完了しました！"
echo ""
echo "ファイル: release/${RELEASE_NAME}.zip"
echo "サイズ: ${SIZE}"
echo ""
echo "このZIPファイルを配布してください。"
echo "=========================================="