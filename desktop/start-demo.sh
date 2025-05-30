#!/bin/bash

echo "TextffCut Desktop Demo Starter"
echo "=============================="

# Python環境チェック
echo "1. Python環境をチェック中..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3が見つかりません"
    exit 1
fi

# FastAPIとuvicornのインストール確認
echo "2. 必要なPythonパッケージをチェック中..."
cd ..
pip install fastapi uvicorn python-multipart

# Terminal 1: FastAPI サーバー起動
echo "3. FastAPIサーバーを起動中..."
cd api
uvicorn main:app --reload --port 8000 &
API_PID=$!
echo "   FastAPI PID: $API_PID"

# サーバーの起動を待つ
sleep 3

# Terminal 2: React開発サーバー起動
echo "4. React開発サーバーを起動中..."
cd ../desktop/frontend
npm start &
REACT_PID=$!
echo "   React PID: $REACT_PID"

# Reactの起動を待つ
sleep 5

# Terminal 3: Electron起動
echo "5. Electronを起動中..."
cd ..
npm run electron-dev &
ELECTRON_PID=$!
echo "   Electron PID: $ELECTRON_PID"

echo ""
echo "✅ すべてのプロセスが起動しました！"
echo ""
echo "停止するには Ctrl+C を押してください"
echo ""

# Ctrl+Cで全プロセスを終了
trap "kill $API_PID $REACT_PID $ELECTRON_PID 2>/dev/null; exit" INT

# プロセスが終了するまで待機
wait