#!/bin/bash
set -e

# TextffCut Docker エントリーポイント
echo "Starting TextffCut..."

# 自動最適化機能の情報を表示
echo "===================================="
echo "🤖 自動最適化機能: 有効"
echo "メモリ使用状況に基づいて自動的に"
echo "最適なパラメータが設定されます"
echo "===================================="

# 環境変数の確認
if [ -n "$TEXTFFCUT_USE_API" ]; then
    echo "API mode enabled: $TEXTFFCUT_USE_API"
fi

if [ -n "$TEXTFFCUT_API_KEY" ]; then
    echo "API key configured: ${TEXTFFCUT_API_KEY:0:10}..."
fi

# ディレクトリの権限確認
for dir in videos output logs temp; do
    if [ ! -w "/app/$dir" ]; then
        echo "Warning: /app/$dir is not writable"
    fi
done

# Streamlitキャッシュディレクトリの作成
mkdir -p ~/.streamlit

# Streamlit設定ファイルの作成（存在しない場合）
if [ ! -f ~/.streamlit/config.toml ]; then
    mkdir -p ~/.streamlit
    cat > ~/.streamlit/config.toml << EOF
[theme]
primaryColor = "#fd444d"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
maxUploadSize = 5000
enableCORS = false
enableXsrfProtection = true
EOF
fi

# コマンド実行
exec "$@"