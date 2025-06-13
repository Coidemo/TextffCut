#!/bin/bash
# TextffCut CLI版 リリースビルドスクリプト

set -e

VERSION="1.0.0"
RELEASE_DIR="release/textffcut_cli_v${VERSION}"

echo "========================================="
echo "TextffCut CLI v${VERSION} ビルド開始"
echo "========================================="

# リリースディレクトリを作成
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# 1. macOS版ビルド
echo ""
echo "1. macOS版をビルド中..."
if [ -f "dist/textffcut_cli_lite" ]; then
    cp dist/textffcut_cli_lite "$RELEASE_DIR/textffcut_cli_macos"
    chmod +x "$RELEASE_DIR/textffcut_cli_macos"
    echo "✅ macOS版ビルド完了"
else
    echo "❌ macOS版が見つかりません。先にビルドしてください。"
fi

# 2. Windowsバッチファイルをコピー
echo ""
echo "2. Windows用ファイルを準備中..."
cp textffcut_cli_windows.bat "$RELEASE_DIR/"
echo "✅ Windowsバッチファイルをコピー"

# 3. READMEを作成
echo ""
echo "3. READMEを作成中..."
cat > "$RELEASE_DIR/README.txt" << 'EOF'
TextffCut CLI v1.0.0
===================

動画の無音部分を検出・削除してFCPXMLをエクスポートするコマンドラインツール

【必要なソフトウェア】
- ffmpeg（必須）

【インストール方法】

macOS:
1. Homebrewをインストール（未インストールの場合）
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

2. ffmpegをインストール
   brew install ffmpeg

3. TextffCutに実行権限を付与
   chmod +x textffcut_cli_macos

Windows:
1. ffmpegをインストール
   https://ffmpeg.org/download.html
   または
   choco install ffmpeg（Chocolatey使用時）

2. textffcut_cli_windows.batを使用するか、
   textffcut_cli_windows.exeを直接実行

【使い方】

1. 動画情報を表示
   macOS:   ./textffcut_cli_macos info video.mp4
   Windows: textffcut_cli_windows.bat info video.mp4

2. 無音部分を検出
   macOS:   ./textffcut_cli_macos silence video.mp4 --threshold -40
   Windows: textffcut_cli_windows.bat silence video.mp4 --threshold -40

3. 無音を削除してFCPXMLをエクスポート
   macOS:   ./textffcut_cli_macos process video.mp4 --remove-silence
   Windows: textffcut_cli_windows.bat process video.mp4 --remove-silence

4. 出力先を指定
   macOS:   ./textffcut_cli_macos process video.mp4 --output-dir ./exports
   Windows: textffcut_cli_windows.bat process video.mp4 --output-dir .\exports

【オプション】
--threshold     無音閾値 (dB) デフォルト: -35
--min-duration  最小無音時間 (秒) デフォルト: 0.3
--output-dir    出力ディレクトリ

【サポート】
問題が発生した場合は、以下を確認してください：
- ffmpegが正しくインストールされているか（ffmpeg -version）
- 動画ファイルのパスが正しいか
- 出力先に書き込み権限があるか

EOF

echo "✅ README作成完了"

# 4. Pythonスクリプト版もコピー（オプション）
echo ""
echo "4. Pythonスクリプト版を準備中..."
cp textffcut_cli_lite.py "$RELEASE_DIR/"
echo "✅ Pythonスクリプト版をコピー"

# 5. サイズ情報を表示
echo ""
echo "========================================="
echo "ビルド完了！"
echo "========================================="
echo "出力先: $RELEASE_DIR"
echo ""
echo "ファイルサイズ:"
ls -lah "$RELEASE_DIR/"

# 6. ZIPファイルを作成
echo ""
echo "5. ZIPファイルを作成中..."
cd release
zip -r "textffcut_cli_v${VERSION}.zip" "textffcut_cli_v${VERSION}"
cd ..
echo "✅ ZIPファイル作成完了: release/textffcut_cli_v${VERSION}.zip"

echo ""
echo "次のステップ:"
echo "1. Windows環境でPyInstallerビルドを実行"
echo "2. textffcut_cli_windows.exeを$RELEASE_DIR/にコピー"
echo "3. 再度ZIPファイルを作成"