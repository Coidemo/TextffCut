#!/bin/bash

echo "🚀 TextffCut を起動しています..."

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.."

# 環境変数を設定
export HOST_VIDEOS_PATH="${PWD}/videos"

# Docker Desktop確認
if ! docker version &>/dev/null; then
    echo "❌ エラー: Docker Desktopが起動していません。"
    echo "Docker Desktopを起動してから、もう一度実行してください。"
    exit 1
fi

# ポート8501を使用しているプロセスをチェック
PORT=8501
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo "⚠️  警告: ポート$PORTが既に使用されています。"
    
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
                    echo "✅ 代替ポート$PORTを使用します。"
                    export TEXTFFCUT_PORT=$PORT
                    break
                fi
            done
        fi
    else
        echo "Docker以外のプロセスがポート$PORTを使用しています。"
        
        # プロセス情報を表示
        echo "使用中のプロセス:"
        lsof -ti:$PORT | xargs ps -p | tail -n +2
        echo ""
        
        # 別のポートを探す
        for ALT_PORT in 8502 8503 8504 8505; do
            if ! lsof -ti:$ALT_PORT > /dev/null 2>&1; then
                PORT=$ALT_PORT
                echo "✅ 代替ポート$PORTを使用します。"
                export TEXTFFCUT_PORT=$PORT
                break
            fi
        done
        
        if [ -z "$TEXTFFCUT_PORT" ]; then
            echo "❌ エラー: 利用可能なポートが見つかりませんでした。"
            echo "他のアプリケーションを終了してから再度お試しください。"
            exit 1
        fi
    fi
fi

# 必要なフォルダを作成
for folder in videos logs prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

echo ""
echo "⏳ 起動を確認しています..."
echo ""

if [ -n "$TEXTFFCUT_PORT" ]; then
    # docker-compose.ymlを一時的に変更（ポート変更対応）
    # docker-compose.override.ymlを作成
    cat > docker-compose.override.yml <<EOF
version: '3.8'
services:
  textffcut:
    ports:
      - "$PORT:8501"
EOF
    
    echo "📍 URL: http://localhost:$PORT"
    echo ""
    
    # docker-composeで起動
    docker-compose up --build
    
    # overrideファイルを削除
    rm -f docker-compose.override.yml
else
    echo "📍 URL: http://localhost:8501"
    echo ""
    
    # 通常のポートで起動
    docker-compose up --build
fi

echo ""
echo "✅ TextffCut を終了しました。"