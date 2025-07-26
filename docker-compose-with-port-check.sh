#!/bin/bash

# 色付き出力
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 TextffCut を起動しています...${NC}"

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

echo -e "${GREEN}📍 URL: http://localhost:$PORT${NC}"
echo ""

# docker-composeで起動
docker-compose up --build

# クリーンアップ
if [ -f docker-compose.override.yml ]; then
    rm -f docker-compose.override.yml
fi