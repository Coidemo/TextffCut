#!/bin/bash
# TextffCut 配布パッケージ作成スクリプト

VERSION=${1:-"1.1.0"}
RELEASE_DIR="release"
PACKAGE_NAME="TextffCut"
# バージョン付きイメージ名
IMAGE_NAME="textffcut:${VERSION}"

echo "🚀 TextffCut v${VERSION} のパッケージを作成します..."

# リリースディレクトリを準備
rm -rf ${RELEASE_DIR}/${PACKAGE_NAME}
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}

# 1. Dockerイメージが存在するか確認
if [[ "$(docker images -q ${IMAGE_NAME} 2> /dev/null)" == "" ]]; then
    echo "⚠️  Dockerイメージが見つかりません。ビルドしてください："
    echo "   docker build -t ${IMAGE_NAME} ."
    exit 1
fi

# 2. Dockerイメージをエクスポート
echo "💾 Dockerイメージを保存中（時間がかかります）..."
echo "   最大圧縮レベルを使用しています..."
echo "   使用イメージ: ${IMAGE_NAME} (3.61GB)"
docker save ${IMAGE_NAME} | gzip -9 > ${RELEASE_DIR}/${PACKAGE_NAME}/textffcut-${VERSION}-docker.tar.gz

# 3. 起動・終了スクリプトをコピー
echo "📝 スクリプトをコピー中..."
cp START_GUI.command ${RELEASE_DIR}/${PACKAGE_NAME}/
cp START_GUI.bat ${RELEASE_DIR}/${PACKAGE_NAME}/
cp UNINSTALL.command ${RELEASE_DIR}/${PACKAGE_NAME}/
cp UNINSTALL.bat ${RELEASE_DIR}/${PACKAGE_NAME}/
cp docker-compose-simple.yml ${RELEASE_DIR}/${PACKAGE_NAME}/

# 実行権限を付与
chmod +x ${RELEASE_DIR}/${PACKAGE_NAME}/*.command

# 4. 必要なディレクトリを作成
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/videos
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/output
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/transcriptions
mkdir -p ${RELEASE_DIR}/${PACKAGE_NAME}/logs

# .gitkeepファイルを追加
touch ${RELEASE_DIR}/${PACKAGE_NAME}/videos/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/output/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/transcriptions/.gitkeep
touch ${RELEASE_DIR}/${PACKAGE_NAME}/logs/.gitkeep

# 5. 使い方ドキュメントを作成
cat > ${RELEASE_DIR}/${PACKAGE_NAME}/使い方.txt << 'EOF'
TextffCut Docker版 使い方
=======================

【必要なもの】
- Docker Desktop（無料）をインストール
  https://www.docker.com/products/docker-desktop/

【使い方】
1. Docker Desktopを起動

2. このフォルダ内の以下のファイルをダブルクリック：
   - Mac: START_GUI.command
   - Windows: START_GUI.bat

3. 初回は読み込みに10-20分かかります（Dockerイメージを展開するため）

4. ブラウザで自動的に開きます
   開かない場合は: http://localhost:8501

5. 動画ファイルは「videos」フォルダに入れてください

【フォルダの説明】
- videos/         動画ファイルを入れる
- output/         処理結果が出力される
- transcriptions/ 文字起こしの保存（キャッシュ）
- logs/          ログファイル

【終了方法】
- ターミナルで Ctrl + C
- または Docker Desktop で停止

【アンインストール】
- Mac: UNINSTALL.command をダブルクリック
- Windows: UNINSTALL.bat をダブルクリック

【トラブルシューティング】
- Docker Desktopが起動しているか確認
- ポート8501が使われていないか確認

=======================
TextffCut Development Team
EOF

# 6. 最終的なZIPを作成
echo "📦 ZIPファイルを作成中..."
cd ${RELEASE_DIR}
zip -r ${PACKAGE_NAME}-v${VERSION}.zip ${PACKAGE_NAME}

# サイズ情報を表示
ZIP_SIZE=$(du -h ${PACKAGE_NAME}-v${VERSION}.zip | cut -f1)

echo "✅ 配布パッケージの作成が完了しました！"
echo "📍 場所: ${RELEASE_DIR}/${PACKAGE_NAME}-v${VERSION}.zip"
echo "📏 サイズ: ${ZIP_SIZE}"
echo ""
echo "🎯 このZIPファイルを購入者に配布してください"