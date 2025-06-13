#!/bin/bash
# TextffCut CLI テストスクリプト

echo "========================================="
echo "TextffCut CLI テスト"
echo "========================================="

# テスト用動画を作成（10秒の動画、5秒無音）
if [ ! -f "test_video.mp4" ]; then
    echo "テスト動画を作成中..."
    ffmpeg -f lavfi -i "sine=frequency=440:duration=2" \
           -f lavfi -i "aevalsrc=0:duration=6" \
           -f lavfi -i "sine=frequency=880:duration=2" \
           -filter_complex "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]" \
           -f lavfi -i "color=c=blue:s=640x480:d=10" \
           -map "[out]" -map 3:v \
           -c:v libx264 -c:a aac \
           test_video.mp4 -y
fi

# CLIのパス
CLI="./dist/textffcut_cli_lite"

echo ""
echo "1. バージョン確認"
$CLI --version

echo ""
echo "2. ヘルプ表示"
$CLI --help

echo ""
echo "3. 動画情報取得"
$CLI info test_video.mp4

echo ""
echo "4. 無音検出"
$CLI silence test_video.mp4 --threshold -35

echo ""
echo "5. FCPXMLエクスポート"
mkdir -p test_output
$CLI process test_video.mp4 --output-dir test_output --remove-silence

echo ""
echo "6. 出力確認"
ls -la test_output/

echo ""
echo "========================================="
echo "テスト完了"
echo "========================================="