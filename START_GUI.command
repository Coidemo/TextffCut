#!/bin/bash
# TextffCut GUI起動スクリプト（ダブルクリックで起動）

cd "$(dirname "$0")"

# 現在のフォルダを表示
echo "📁 作業フォルダ: $(pwd)"
echo "   動画は: $(pwd)/videos に入れてください"
echo "   結果は: $(pwd)/output に出力されます"
echo ""

echo "🚀 TextffCut を起動しています..."
echo ""
echo "初回起動時はDockerイメージの読み込みに時間がかかります。"
echo ""

# Dockerイメージが存在しない場合は読み込む
if [[ "$(docker images -q textffcut:1.1.0 2> /dev/null)" == "" ]]; then
    if [ -f "textffcut-1.1.0-docker.tar.gz" ]; then
        echo "📦 Dockerイメージを読み込んでいます..."
        docker load < textffcut-1.1.0-docker.tar.gz
    fi
fi

# 既存のコンテナをチェックして削除
if docker ps -a | grep -q textffcut_app; then
    echo "⚠️  既に起動中または停止中のコンテナがあります"
    echo "   既存のコンテナを削除して再起動します..."
    docker stop textffcut_app 2>/dev/null || true
    docker rm textffcut_app 2>/dev/null || true
fi

# Docker Composeで起動
echo "🌐 起動中..."
echo ""
echo "ブラウザで以下のURLを開いてください："
echo "👉 http://localhost:8501"
echo ""
echo "（終了するには Ctrl+C を押してください）"
echo ""
docker-compose -f docker-compose-simple.yml up

echo ""
echo "終了しました。このウィンドウを閉じてください。"