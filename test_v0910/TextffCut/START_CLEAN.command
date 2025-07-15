#!/bin/bash

echo "==========================================="
echo "TextffCut v0.9.10 クリーン起動"
echo "==========================================="
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# 環境変数を設定
export HOST_VIDEOS_PATH="${SCRIPT_DIR}/videos"

echo "🧹 既存のTextffCutコンテナとイメージをクリーンアップしています..."
echo ""

# textffcutという名前を含むコンテナを停止・削除
echo "▶ コンテナを停止・削除中..."
TEXTFFCUT_CONTAINERS=$(docker ps -a --filter "name=textffcut" --format "{{.Names}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_CONTAINERS" ]; then
    echo "$TEXTFFCUT_CONTAINERS" | while read container; do
        echo "  - $container を停止中..."
        docker stop "$container" >/dev/null 2>&1 || true
        echo "  - $container を削除中..."
        docker rm "$container" >/dev/null 2>&1 || true
    done
fi

# docker-composeで管理されているコンテナも削除
docker-compose -f docker-compose-simple.yml down >/dev/null 2>&1 || true

# textffcutという名前を含むイメージを削除
echo ""
echo "▶ イメージを削除中..."
TEXTFFCUT_IMAGES=$(docker images --filter "reference=*textffcut*" --format "{{.Repository}}:{{.Tag}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_IMAGES" ]; then
    echo "$TEXTFFCUT_IMAGES" | while read image; do
        echo "  - $image を削除中..."
        docker rmi "$image" >/dev/null 2>&1 || true
    done
fi

# ボリュームの削除
echo ""
echo "▶ ボリュームを削除中..."
TEXTFFCUT_VOLUMES=$(docker volume ls --filter "name=textffcut" --format "{{.Name}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_VOLUMES" ]; then
    echo "$TEXTFFCUT_VOLUMES" | while read volume; do
        echo "  - $volume を削除中..."
        docker volume rm "$volume" >/dev/null 2>&1 || true
    done
fi

echo ""
echo "✅ クリーンアップ完了！"
echo ""
echo "==========================================="
echo "TextffCut を起動しています..."
echo "==========================================="
echo ""

# Docker イメージをロード
if [ -f "textffcut_v0.9.10_docker.tar.gz" ]; then
    echo "📦 Docker イメージを読み込んでいます..."
    echo "（初回は数分かかります）"
    docker load < textffcut_v0.9.10_docker.tar.gz
    echo ""
else
    echo "❌ Docker イメージファイルが見つかりません。"
    echo "textffcut_v0.9.10_docker.tar.gz が同じフォルダにあることを確認してください。"
    echo ""
    read -p "Enterキーを押して終了..."
    exit 1
fi

# 必要なフォルダを作成
for folder in videos logs models prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

# システムメモリをチェック
MEMORY_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
echo "💻 システムメモリ: ${MEMORY_GB}GB"

# Docker Desktopに割り当てられたメモリを取得
DOCKER_MEM_BYTES=$(docker system info 2>/dev/null | grep "Total Memory" | awk '{print $3}' | sed 's/GiB//')
if [ -n "$DOCKER_MEM_BYTES" ]; then
    DOCKER_MEM_GB=$(echo "$DOCKER_MEM_BYTES" | awk '{print int($1)}')
else
    DOCKER_MEM_GB=$(( MEMORY_GB / 2 ))
fi

# 推奨メモリを計算
RECOMMENDED_MEM=$(( DOCKER_MEM_GB * 80 / 100 ))
if [ $RECOMMENDED_MEM -lt 1 ]; then
    RECOMMENDED_MEM=1
fi

echo "Docker Desktop割り当て: ${DOCKER_MEM_GB}GB"
echo "割り当てメモリ: ${RECOMMENDED_MEM}GB"

# docker-compose.override.ymlを生成
cat > docker-compose.override.yml <<OVERRIDE_EOF
version: '3.8'
services:
  textffcut:
    deploy:
      resources:
        limits:
          memory: ${RECOMMENDED_MEM}g
    environment:
      - TEXTFFCUT_MEMORY_LIMIT=${RECOMMENDED_MEM}g
OVERRIDE_EOF

echo ""
echo "🚀 TextffCut を起動しています..."

# Docker Composeで起動
docker-compose -f docker-compose-simple.yml -f docker-compose.override.yml up -d

# 起動確認
echo ""
echo "⏳ 起動を確認しています..."
sleep 5

if docker ps | grep -q textffcut; then
    echo ""
    echo "✅ TextffCut が正常に起動しました！"
    echo ""
    echo "==========================================="
    echo "📌 アクセス方法"
    echo "==========================================="
    echo ""
    echo "ブラウザで以下のURLを開いてください："
    echo "http://localhost:8501"
    echo ""
    echo "動画ファイルは videos フォルダに入れてください。"
    echo ""
    echo "==========================================="
    echo ""
    
    # ブラウザを開く
    open "http://localhost:8501"
    
    echo "終了するには、このウィンドウを閉じてください。"
    echo "（TextffCutは引き続き実行されます）"
    echo ""
    echo "TextffCutを停止する場合は、Docker Desktop から"
    echo "textffcut コンテナを停止してください。"
else
    echo ""
    echo "❌ TextffCut の起動に失敗しました。"
    echo ""
    echo "Docker Desktop が正常に動作していることを確認してください。"
    echo ""
fi

# overrideファイルを削除
rm -f ./docker-compose.override.yml

read -p "Enterキーを押して終了..."
