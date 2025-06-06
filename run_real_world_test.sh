#!/bin/bash
# 実動作テスト実行スクリプト

echo "=== TextffCut 実動作テスト ==="
echo "開始時刻: $(date)"
echo ""

# デバッグモードを有効化
export TEXTFFCUT_DEBUG=1

# ログディレクトリを作成
mkdir -p test_logs
LOG_FILE="test_logs/test_$(date +%Y%m%d_%H%M%S).log"

# テスト用動画の作成
echo "1. テスト用動画を作成中..."
python create_test_video.py | tee -a "$LOG_FILE"

# 必要な環境変数の確認
echo ""
echo "2. 環境確認..."
echo "Python: $(python --version)"
echo "FFmpeg: $(ffmpeg -version | head -1)"
echo "APIキー設定: ${OPENAI_API_KEY:+設定済み}"

# アプリケーションの起動
echo ""
echo "3. アプリケーションを起動します..."
echo "ブラウザで http://localhost:8501 を開いてください"
echo ""
echo "テスト手順:"
echo "- APIモードでtest_short_30s.mp4を文字起こし"
echo "- アライメント処理が自動実行されることを確認"
echo "- wordsフィールドの生成を確認"
echo ""
echo "ログは $LOG_FILE に記録されます"
echo "Ctrl+C で終了"
echo ""

# Streamlitアプリケーションを起動（ログ付き）
streamlit run main.py 2>&1 | tee -a "$LOG_FILE"