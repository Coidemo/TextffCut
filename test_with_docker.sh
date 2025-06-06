#!/bin/bash
# Docker環境での実動作テストスクリプト

echo "=== TextffCut Docker環境テスト ==="
echo ""

# テスト動画が存在するか確認
if [ ! -f "videos/test_short_30s.mp4" ]; then
    echo "テスト動画を作成しています..."
    python create_test_video.py
fi

# Docker Composeファイルの確認
if [ -f "docker-compose-simple.yml" ]; then
    COMPOSE_FILE="docker-compose-simple.yml"
elif [ -f "docker-compose.yml" ]; then
    COMPOSE_FILE="docker-compose.yml"
else
    echo "❌ Docker Composeファイルが見つかりません"
    exit 1
fi

echo "使用するDocker Composeファイル: $COMPOSE_FILE"
echo ""

# デバッグモードを有効化
export TEXTFFCUT_DEBUG=1

# Dockerイメージのビルドと起動
echo "Dockerイメージをビルドして起動します..."
docker-compose -f $COMPOSE_FILE up --build

# 終了時のクリーンアップ
echo ""
echo "コンテナを停止しています..."
docker-compose -f $COMPOSE_FILE down