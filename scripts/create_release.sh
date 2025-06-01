#!/bin/bash
# TextffCut リリースパッケージ作成スクリプト

VERSION=${1:-"1.0.0"}
RELEASE_DIR="release"
PACKAGE_NAME="TextffCut-v${VERSION}"

echo "🚀 TextffCut v${VERSION} のリリースパッケージを作成します..."

# リリースディレクトリをクリーンアップ
rm -rf ${RELEASE_DIR}
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}

# 必要なファイルをコピー
echo "📁 ファイルをコピー中..."
cp -r main.py ${RELEASE_DIR}/${PACKAGE_NAME}/
cp -r core ${RELEASE_DIR}/${PACKAGE_NAME}/
cp -r ui ${RELEASE_DIR}/${PACKAGE_NAME}/
cp -r utils ${RELEASE_DIR}/${PACKAGE_NAME}/
cp -r scripts ${RELEASE_DIR}/${PACKAGE_NAME}/
cp -r docs ${RELEASE_DIR}/${PACKAGE_NAME}/
cp config.py ${RELEASE_DIR}/${PACKAGE_NAME}/
cp requirements.txt ${RELEASE_DIR}/${PACKAGE_NAME}/
cp LICENSE ${RELEASE_DIR}/${PACKAGE_NAME}/
cp README.md ${RELEASE_DIR}/${PACKAGE_NAME}/
cp .env.example ${RELEASE_DIR}/${PACKAGE_NAME}/

# Docker関連ファイル
cp Dockerfile ${RELEASE_DIR}/${PACKAGE_NAME}/
cp docker-compose.yml ${RELEASE_DIR}/${PACKAGE_NAME}/
cp .dockerignore ${RELEASE_DIR}/${PACKAGE_NAME}/

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

# 不要なファイルを削除
echo "🧹 不要なファイルを削除中..."
find ${RELEASE_DIR}/${PACKAGE_NAME} -name "*.pyc" -delete
find ${RELEASE_DIR}/${PACKAGE_NAME} -name "__pycache__" -type d -exec rm -rf {} +
find ${RELEASE_DIR}/${PACKAGE_NAME} -name ".DS_Store" -delete

# ZIPファイルを作成
echo "📦 ZIPファイルを作成中..."
cd ${RELEASE_DIR}
zip -r ${PACKAGE_NAME}.zip ${PACKAGE_NAME}

# チェックサムを生成
echo "🔐 チェックサムを生成中..."
shasum -a 256 ${PACKAGE_NAME}.zip > ${PACKAGE_NAME}.zip.sha256

echo "✅ リリースパッケージの作成が完了しました！"
echo "📍 場所: ${RELEASE_DIR}/${PACKAGE_NAME}.zip"
echo "📏 サイズ: $(du -h ${PACKAGE_NAME}.zip | cut -f1)"
echo "🔑 SHA256: $(cat ${PACKAGE_NAME}.zip.sha256)"