#!/bin/bash

# 両方のアプリケーションを起動するスクリプト

echo "=== TextffCut 起動スクリプト ==="
echo ""
echo "1. main版（動画編集用）を起動中..."
echo "   URL: http://localhost:8501"
cd ../TextffCut-main
nohup streamlit run main.py --server.port 8501 --server.headless true > ../TextffCut/logs/main_app.log 2>&1 &
MAIN_PID=$!
echo "   PID: $MAIN_PID"

echo ""
echo "2. MVP版（リファクタリング版）を起動中..."
echo "   URL: http://localhost:8502"
cd ../TextffCut
nohup streamlit run main_mvp.py --server.port 8502 --server.headless true > logs/mvp_app.log 2>&1 &
MVP_PID=$!
echo "   PID: $MVP_PID"

echo ""
echo "=== 起動完了 ==="
echo ""
echo "アプリケーション:"
echo "  - main版（安定版）: http://localhost:8501"
echo "  - MVP版（開発版）: http://localhost:8502"
echo ""
echo "停止方法:"
echo "  kill $MAIN_PID $MVP_PID"
echo ""
echo "ログ確認:"
echo "  - main版: tail -f logs/main_app.log"
echo "  - MVP版: tail -f logs/mvp_app.log"