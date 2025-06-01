#!/bin/bash
# TextffCut Docker イメージリリースパッケージ作成スクリプト

VERSION=${1:-"1.1.0"}
RELEASE_DIR="release"
IMAGE_NAME="textffcut/textffcut"
PACKAGE_NAME="TextffCut-Docker-v${VERSION}"

echo "🐳 TextffCut Docker v${VERSION} のリリースパッケージを作成します..."

# リリースディレクトリを作成
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}

# Dockerイメージをビルド
echo "🔨 Dockerイメージをビルド中..."
docker build -t ${IMAGE_NAME}:${VERSION} -t ${IMAGE_NAME}:latest .

if [ $? -ne 0 ]; then
    echo "❌ Dockerイメージのビルドに失敗しました"
    exit 1
fi

# イメージサイズを確認
IMAGE_SIZE=$(docker images ${IMAGE_NAME}:${VERSION} --format "{{.Size}}")
echo "📏 イメージサイズ: ${IMAGE_SIZE}"

# Dockerイメージを保存
echo "💾 Dockerイメージを保存中..."
docker save ${IMAGE_NAME}:${VERSION} | gzip > ${RELEASE_DIR}/${PACKAGE_NAME}/textffcut-${VERSION}.tar.gz

# 起動スクリプトを作成
cat > ${RELEASE_DIR}/${PACKAGE_NAME}/start-textffcut.sh << 'EOF'
#!/bin/bash
# TextffCut 起動スクリプト

VERSION="1.1.0"
IMAGE_NAME="textffcut/textffcut"

echo "🚀 TextffCut を起動します..."

# イメージが存在しない場合はロード
if [[ "$(docker images -q ${IMAGE_NAME}:${VERSION} 2> /dev/null)" == "" ]]; then
    echo "📦 Dockerイメージをロード中..."
    docker load < textffcut-${VERSION}.tar.gz
fi

# コンテナを起動
echo "🌐 http://localhost:8501 でアクセスできます"
docker run --rm \
    -p 8501:8501 \
    -v "$(pwd)/videos:/app/videos" \
    -v "$(pwd)/output:/app/output" \
    -v "$(pwd)/transcriptions:/app/transcriptions" \
    -v "$(pwd)/logs:/app/logs" \
    --name textffcut \
    ${IMAGE_NAME}:${VERSION}
EOF

# Windowsバッチファイルも作成
cat > ${RELEASE_DIR}/${PACKAGE_NAME}/start-textffcut.bat << 'EOF'
@echo off
echo 🚀 TextffCut を起動します...

REM イメージの確認とロード
docker images textffcut/textffcut:1.1.0 >nul 2>&1
if errorlevel 1 (
    echo 📦 Dockerイメージをロード中...
    docker load -i textffcut-1.1.0.tar.gz
)

REM コンテナを起動
echo 🌐 http://localhost:8501 でアクセスできます
docker run --rm ^
    -p 8501:8501 ^
    -v "%cd%\videos:/app/videos" ^
    -v "%cd%\output:/app/output" ^
    -v "%cd%\transcriptions:/app/transcriptions" ^
    -v "%cd%\logs:/app/logs" ^
    --name textffcut ^
    textffcut/textffcut:1.1.0
EOF

# 使用方法を作成
cat > ${RELEASE_DIR}/${PACKAGE_NAME}/README.txt << EOF
TextffCut Docker版 v${VERSION}
================================

【必要なソフトウェア】
- Docker Desktop

【使い方】
1. このフォルダで以下のコマンドを実行:
   
   Mac/Linux:
   ./start-textffcut.sh
   
   Windows:
   start-textffcut.bat

2. ブラウザで http://localhost:8501 にアクセス

3. 動画ファイルは videos/ フォルダに配置

【フォルダ構成】
- videos/         : 動画ファイルを配置
- output/         : 処理結果が保存される
- transcriptions/ : 文字起こしキャッシュ
- logs/          : ログファイル

【初回起動時】
Dockerイメージのロードに数分かかります。

【ライセンス】
本ソフトウェアは購入者限定のライセンスです。
再配布は禁止されています。

================================
TextffCut Development Team
EOF

# 必要なディレクトリを作成
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/videos
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/output
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/transcriptions
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/logs

# .gitkeepファイルを追加
touch ${RELEASE_DIR}/${PACKAGE_NAME}/videos/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/output/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/transcriptions/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/logs/.gitkeep

# 実行権限を付与
chmod +x ${RELEASE_DIR}/${PACKAGE_NAME}/start-textffcut.sh

# チェックサムを生成
echo "🔐 チェックサムを生成中..."
cd ${RELEASE_DIR}/${PACKAGE_NAME}
shasum -a 256 textffcut-${VERSION}.tar.gz > checksum.sha256
cd ../..

# 最終的なZIPを作成
echo "📦 最終的なZIPファイルを作成中..."
cd ${RELEASE_DIR}
zip -r ${PACKAGE_NAME}.zip ${PACKAGE_NAME}

# サイズ情報
TAR_SIZE=$(du -h ${PACKAGE_NAME}/textffcut-${VERSION}.tar.gz | cut -f1)
ZIP_SIZE=$(du -h ${PACKAGE_NAME}.zip | cut -f1)

echo "✅ Docker版リリースパッケージの作成が完了しました！"
echo "📍 場所: ${RELEASE_DIR}/${PACKAGE_NAME}.zip"
echo "📏 Dockerイメージ（圧縮済み）: ${TAR_SIZE}"
echo "📏 最終ZIPサイズ: ${ZIP_SIZE}"
echo ""
echo "⚠️  注意: このファイルは非常に大きいです（数GB）"
echo "   配布にはクラウドストレージの利用を推奨します"