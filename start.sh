#!/bin/bash

echo "🎬 TextffCut を起動します..."

# 必要なフォルダを自動作成
if [ ! -d "videos" ]; then
    echo "📁 videos フォルダを作成しています..."
    mkdir videos
fi

if [ ! -d "transcriptions" ]; then
    echo "📁 transcriptions フォルダを作成しています..."
    mkdir transcriptions
fi

# ポートが使用中かチェック
if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  ポート 8501 が既に使用されています"
    echo "別のポート（8502）で起動しますか？ (y/n)"
    read -r response
    if [[ "$response" == "y" ]]; then
        PORT=8502
    else
        echo "既存のアプリケーションを停止してから再度実行してください"
        exit 1
    fi
else
    PORT=8501
fi

echo "🚀 TextffCut を起動中..."
echo "📍 ブラウザで http://localhost:$PORT を開いてください"
echo ""
echo "停止するには Ctrl+C を押してください"
echo ""

# Dockerコンテナを起動
docker run -p $PORT:8501 \
  -v "$(pwd)/videos:/app/videos" \
  -v "$(pwd)/transcriptions:/app/transcriptions" \
  textffcut:latest