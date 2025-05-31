#!/bin/bash

# TextffCut Docker実行スクリプト
# 簡単にDockerコンテナを起動・管理するためのヘルパー

set -e

# 色付き出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘッダー
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}   TextffCut Docker Manager${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# コマンドライン引数の処理
COMMAND=${1:-help}

# 関数定義
show_help() {
    echo "使用方法: ./docker-run.sh [コマンド]"
    echo ""
    echo "コマンド:"
    echo "  start    - コンテナをビルドして起動"
    echo "  stop     - コンテナを停止"
    echo "  restart  - コンテナを再起動"
    echo "  logs     - ログを表示"
    echo "  shell    - コンテナ内でシェルを起動"
    echo "  clean    - コンテナと関連データを削除"
    echo "  status   - コンテナの状態を確認"
    echo "  help     - このヘルプを表示"
}

# 必要なディレクトリの作成
create_directories() {
    echo "必要なディレクトリを作成中..."
    mkdir -p videos output logs temp
    echo -e "${GREEN}✓ ディレクトリを作成しました${NC}"
}

# .envファイルの確認
check_env_file() {
    if [ ! -f .env ] && [ -f .env.example ]; then
        echo -e "${YELLOW}📝 .envファイルが見つかりません。.env.exampleからコピーします...${NC}"
        cp .env.example .env
        echo -e "${GREEN}✓ .envファイルを作成しました${NC}"
        echo -e "${YELLOW}⚠️  必要に応じて.envファイルを編集してください${NC}"
    fi
}

# Docker Composeのバージョン確認
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Dockerがインストールされていません${NC}"
        echo "Docker Desktopをインストールしてください: https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Composeがインストールされていません${NC}"
        exit 1
    fi
}

# コンテナの起動
start_container() {
    check_docker
    create_directories
    check_env_file
    
    echo ""
    echo "コンテナをビルドして起動中..."
    
    if docker compose version &> /dev/null; then
        docker compose up -d --build
    else
        docker-compose up -d --build
    fi
    
    echo ""
    echo -e "${GREEN}✓ TextffCutが起動しました！${NC}"
    echo ""
    echo "アクセス方法:"
    echo -e "  ${BLUE}http://localhost:8501${NC}"
    echo ""
    echo "動画ファイルの配置:"
    echo "  ./videos/ フォルダに動画ファイルを配置してください"
    echo ""
}

# コンテナの停止
stop_container() {
    echo "コンテナを停止中..."
    
    if docker compose version &> /dev/null; then
        docker compose down
    else
        docker-compose down
    fi
    
    echo -e "${GREEN}✓ コンテナを停止しました${NC}"
}

# コンテナの再起動
restart_container() {
    stop_container
    echo ""
    start_container
}

# ログの表示
show_logs() {
    if docker compose version &> /dev/null; then
        docker compose logs -f
    else
        docker-compose logs -f
    fi
}

# シェルアクセス
shell_access() {
    echo "コンテナ内のシェルに接続中..."
    
    if docker compose version &> /dev/null; then
        docker compose exec app bash
    else
        docker-compose exec app bash
    fi
}

# クリーンアップ
clean_all() {
    echo -e "${YELLOW}⚠️  警告: この操作はコンテナとボリュームを削除します${NC}"
    read -p "本当に続行しますか？ (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if docker compose version &> /dev/null; then
            docker compose down -v
        else
            docker-compose down -v
        fi
        
        echo -e "${GREEN}✓ クリーンアップが完了しました${NC}"
    else
        echo "キャンセルしました"
    fi
}

# ステータス確認
check_status() {
    echo "コンテナの状態:"
    echo ""
    
    if docker compose version &> /dev/null; then
        docker compose ps
    else
        docker-compose ps
    fi
}

# メイン処理
case "$COMMAND" in
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    logs)
        show_logs
        ;;
    shell)
        shell_access
        ;;
    clean)
        clean_all
        ;;
    status)
        check_status
        ;;
    help|*)
        show_help
        ;;
esac