#!/bin/bash

echo "TextffCut v0.9.10 を起動します..."
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# 環境変数を設定
export HOST_VIDEOS_PATH="${SCRIPT_DIR}/videos"

# ===========================================
# メモリ最適化設定
# ===========================================
echo "💾 Docker Desktopのメモリ設定を確認しています..."

# Docker Desktopに割り当てられたメモリを取得
DOCKER_MEM_BYTES=$(docker system info 2>/dev/null | grep "Total Memory" | awk '{print $3}' | sed 's/GiB//')
if [ -n "$DOCKER_MEM_BYTES" ]; then
    # GiBからGBに変換（小数点以下切り捨て）
    DOCKER_MEM_GB=$(echo "$DOCKER_MEM_BYTES" | awk '{print int($1)}')
else
    # 取得できない場合はMacの物理メモリから推定
    TOTAL_MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    # Docker Desktopのデフォルトは物理メモリの半分程度
    DOCKER_MEM_GB=$(( TOTAL_MEM_GB / 2 ))
    echo "   ⚠️  Docker Desktopのメモリ設定を取得できませんでした"
    echo "   物理メモリ(${TOTAL_MEM_GB}GB)から推定: ${DOCKER_MEM_GB}GB"
fi

echo "   Docker Desktop割り当て: ${DOCKER_MEM_GB}GB"

# Docker Desktopの割り当てメモリに基づいて推奨値を計算（80%を基本）
RECOMMENDED_MEM=$(( DOCKER_MEM_GB * 80 / 100 ))

# 最低1GBは確保（極小環境用の安全策）
if [ $RECOMMENDED_MEM -lt 1 ]; then
    RECOMMENDED_MEM=1
fi

# 推奨値がDocker割り当てを超えないようにチェック（念のため）
if [ $RECOMMENDED_MEM -gt $DOCKER_MEM_GB ]; then
    RECOMMENDED_MEM=$DOCKER_MEM_GB
    echo "   ⚠️  Docker Desktop割り当てを超えないよう、${RECOMMENDED_MEM}GBに調整しました"
fi

echo "   割り当てメモリ: ${RECOMMENDED_MEM}GB"
echo ""

# docker-compose.override.ymlを生成（メモリ制限を追加）
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

# ===========================================
# Docker Desktop確認
# ===========================================
if ! docker version &>/dev/null; then
    echo "エラー: Docker Desktopが起動していません。"
    echo "Docker Desktopを起動してから、もう一度実行してください。"
    
    # Docker Desktopのメモリ設定アドバイス
    echo ""
    echo "💡 Docker Desktopのメモリ設定を確認してください："
    echo "   1. Docker Desktop → Settings → Resources"
    echo "   2. Memory を ${RECOMMENDED_MEM}GB 以上に設定"
    echo ""
    
    read -p "Enterキーを押して終了..."
    exit 1
fi

# 既存のTextffCutコンテナをチェック
RUNNING_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "^TextffCut$" || true)
if [ -n "$RUNNING_CONTAINER" ]; then
    echo "既存のTextffCutコンテナが起動中です。"
    echo ""
    echo "=== 起動設定 ==="
    echo "📍 URL: http://localhost:8501"
    echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
    echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    echo ""
    echo "既に起動しているため、そのまま使用します。"
    echo "終了するには Ctrl+C を押してください。"
    read -p "Enterキーを押して終了..."
    exit 0
fi

# 停止したコンテナがあるかチェック
STOPPED_CONTAINER=$(docker ps -a --format "{{.Names}}" | grep -E "^TextffCut$" || true)
if [ -n "$STOPPED_CONTAINER" ]; then
    echo "停止中のTextffCutコンテナを再起動しています..."
    docker start TextffCut
    echo ""
    echo "=== 起動設定 ==="
    echo "📍 URL: http://localhost:8501"
    echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
    echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    
    # ログを表示
    docker logs -f TextffCut
    read -p "Enterキーを押して終了..."
    exit 0
fi

# ポート8501を使用しているプロセスをチェック
PORT=8501
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo "警告: ポート$PORTが既に使用されています。"
    
    # Dockerコンテナが使用しているかチェック
    CONTAINER_USING_PORT=$(docker ps --format "{{.Names}}" | while read container; do
        if docker port "$container" 2>/dev/null | grep -q "$PORT"; then
            echo "$container"
            break
        fi
    done)
    
    if [ -n "$CONTAINER_USING_PORT" ]; then
        # TextffCutのコンテナかチェック
        if [[ "$CONTAINER_USING_PORT" == textffcut* ]] || [[ "$CONTAINER_USING_PORT" == "TextffCut" ]]; then
            echo "既存のTextffCutコンテナ($CONTAINER_USING_PORT)が起動しています。"
            echo "自動的に停止して新しいコンテナを起動します..."
            docker stop "$CONTAINER_USING_PORT"
            docker rm "$CONTAINER_USING_PORT" 2>/dev/null
        else
            echo "別のDockerコンテナ($CONTAINER_USING_PORT)がポート$PORTを使用しています。"
            # 別のポートを探す
            for ALT_PORT in 8502 8503 8504 8505; do
                if ! lsof -ti:$ALT_PORT > /dev/null 2>&1; then
                    PORT=$ALT_PORT
                    echo "代替ポート$PORTを使用します。"
                    export TEXTFFCUT_PORT=$PORT
                    break
                fi
            done
        fi
    else
        echo "Docker以外のプロセスがポート$PORTを使用しています。"
        # 別のポートを探す
        for ALT_PORT in 8502 8503 8504 8505; do
            if ! lsof -ti:$ALT_PORT > /dev/null 2>&1; then
                PORT=$ALT_PORT
                echo "代替ポート$PORTを使用します。"
                export TEXTFFCUT_PORT=$PORT
                break
            fi
        done
    fi
fi

# 必要なフォルダを作成
for folder in videos logs models prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

# 現在のバージョンのイメージが存在するかチェック
if docker images | grep -q "textffcut.*0.9.10"; then
    echo "既存のイメージ textffcut:0.9.10 を使用します。"
fi

# イメージをロード（まだロードされていない場合）
if ! docker images | grep -q "textffcut.*0.9.10"; then
    echo "Dockerイメージをロードしています（初回のみ）..."
    docker load -i textffcut_v0.9.10_docker.tar.gz
fi

echo ""
echo "=== 起動設定 ==="
echo "📍 URL: http://localhost:$PORT"
echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
echo ""

# メモリ不足の警告
if [ $RECOMMENDED_MEM -lt 4 ]; then
    echo "⚠️  警告: 割り当てメモリが4GB未満です"
    echo "   大きな動画の処理に失敗する可能性があります"
    echo "   Docker Desktopのメモリ設定を増やすか、他のアプリケーションを終了してください"
    echo ""
    echo "   ヒント: 2時間以上の動画は12GB以上推奨"
    echo ""
fi

echo "アプリケーションを起動しています..."
echo "ブラウザで http://localhost:$PORT を開いています..."
open "http://localhost:$PORT"

if [ -n "$TEXTFFCUT_PORT" ]; then
    # docker-compose.ymlを一時的に作成（ポート変更対応）
    sed "s/8501:8501/$TEXTFFCUT_PORT:8501/g" ./docker-compose.yml > ./docker-compose-temp.yml
    
    # overrideファイルと一緒に起動
    docker-compose -f ./docker-compose-temp.yml -f ./docker-compose.override.yml up
    
    # 一時ファイルを削除
    rm -f ./docker-compose-temp.yml
    rm -f ./docker-compose.override.yml
else
    # overrideファイルと一緒に起動
    docker-compose -f ./docker-compose.yml -f ./docker-compose.override.yml up
    
    # overrideファイルを削除
    rm -f ./docker-compose.override.yml
fi

read -p "Enterキーを押して終了..."
