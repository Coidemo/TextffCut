#!/bin/bash
# TextffCut アンインストールスクリプト

cd "$(dirname "$0")"

echo "🗑️  TextffCut のアンインストール"
echo "================================"
echo ""
echo "以下を削除します："
echo "1. Dockerコンテナ"
echo "2. Dockerイメージ（約4GB）"
echo "3. このフォルダ内の作業データ"
echo ""
echo "⚠️  注意: videosフォルダ内の動画は削除されません"
echo ""
read -p "続行しますか？ (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🧹 クリーンアップ中..."
    
    # コンテナを停止・削除
    echo "- コンテナを削除..."
    docker-compose -f docker-compose-simple.yml down 2>/dev/null || true
    
    # イメージを削除
    echo "- Dockerイメージを削除..."
    docker rmi textffcut:1.1.0 2>/dev/null || true
    
    # 作業ファイルを削除（videosは除く）
    echo "- 作業ファイルを削除..."
    rm -rf output/* transcriptions/* logs/*
    
    echo ""
    echo "✅ アンインストール完了！"
    echo ""
    echo "このフォルダ自体を削除するには："
    echo "1. このウィンドウを閉じる"
    echo "2. TextffCut-Docker-Complete フォルダをゴミ箱に入れる"
else
    echo "❌ アンインストールをキャンセルしました"
fi

echo ""
echo "Enterキーを押して終了..."
read