#!/bin/bash
# TextffCut v0.9.7 最適化版ビルドスクリプト

echo "=== TextffCut v0.9.7 最適化版ビルド ==="
echo "全機能維持（Whisper medium + アライメント）でサイズ削減"

# ビルド前のクリーンアップ
echo "1. ビルド前のクリーンアップ..."
docker system prune -f

# 現在のイメージサイズを確認（あれば）
echo "2. 現在のイメージサイズ:"
docker images | grep textffcut || echo "既存イメージなし"

# ビルド実行
echo "3. 最適化版イメージをビルド中..."
docker-compose -f docker-compose-v097.yml build --no-cache

# ビルド後のサイズ確認
echo "4. ビルド完了！新しいイメージサイズ:"
docker images | grep textffcut

# 削減効果の確認
echo ""
echo "=== サイズ削減の内訳 ==="
echo "- CPU版PyTorch使用: 1-2GB削減"
echo "- マルチステージビルド: 0.5-1GB削減"  
echo "- 不要ファイル削除: 200-500MB削減"
echo "- Python最適化: 100-200MB削減"
echo ""
echo "予想サイズ: 8-10GB（元13.1GBから3-5GB削減）"
echo ""
echo "起動: docker-compose -f docker-compose-v097.yml up"