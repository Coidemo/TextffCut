#!/bin/bash

# 色付き出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}   TextffCut Clean Start${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.."

# クリーンアップ
echo -e "${YELLOW}🧹 既存のコンテナとイメージをクリーンアップしています...${NC}"

# TextffCutコンテナを停止・削除
docker ps -a --format "{{.Names}}" | grep -i textffcut | while read container; do
    echo "   - コンテナを削除: $container"
    docker stop "$container" >/dev/null 2>&1
    docker rm "$container" >/dev/null 2>&1
done

# docker-composeで管理されているコンテナを削除
if [ -f docker-compose.yml ]; then
    if docker compose version &> /dev/null; then
        docker compose down -v >/dev/null 2>&1
    else
        docker-compose down -v >/dev/null 2>&1
    fi
fi

# TextffCutイメージを削除
docker images --format "{{.Repository}}:{{.Tag}}" | grep -i textffcut | while read image; do
    echo "   - イメージを削除: $image"
    docker rmi "$image" >/dev/null 2>&1
done

# ボリュームを削除
docker volume ls --format "{{.Name}}" | grep -i textffcut | while read volume; do
    echo "   - ボリュームを削除: $volume"
    docker volume rm "$volume" >/dev/null 2>&1
done

echo -e "${GREEN}✓ クリーンアップ完了${NC}"
echo ""

# ポートチェック関数
find_available_port() {
    local base_port=$1
    local port=$base_port
    local max_attempts=10
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if ! lsof -ti:$port > /dev/null 2>&1; then
            echo $port
            return 0
        fi
        port=$((port + 1))
        attempt=$((attempt + 1))
    done
    
    return 1
}

# 使用するポートを決定
PORT=$(find_available_port 8501)

if [ -z "$PORT" ]; then
    echo -e "${RED}❌ エラー: 利用可能なポートが見つかりませんでした。${NC}"
    exit 1
fi

if [ "$PORT" != "8501" ]; then
    echo -e "${YELLOW}⚠️  ポート8501が使用中のため、ポート$PORTを使用します。${NC}"
    
    # docker-compose.override.ymlを作成
    cat > docker-compose.override.yml <<EOF
services:
  textffcut:
    ports:
      - "$PORT:8501"
EOF
fi

# 必要なフォルダを作成
for folder in videos logs prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

echo ""
echo -e "${GREEN}🚀 クリーンビルドで起動しています...${NC}"
echo -e "${GREEN}📍 URL: http://localhost:$PORT${NC}"
echo ""

# docker-composeで起動（--buildオプションで強制ビルド）
if docker compose version &> /dev/null; then
    docker compose up --build --force-recreate
else
    docker-compose up --build --force-recreate
fi

# クリーンアップ
if [ -f docker-compose.override.yml ]; then
    rm -f docker-compose.override.yml
fi