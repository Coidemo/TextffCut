#!/bin/bash
# TextffCutをモデル事前読み込み付きで起動するスクリプト

echo "WhisperXモデルを事前読み込み中..."
python scripts/preload_models.py

if [ $? -eq 0 ]; then
    echo "モデルの事前読み込みが完了しました"
    echo "TextffCutを起動します..."
    streamlit run main.py
else
    echo "モデルの事前読み込みに失敗しました"
    exit 1
fi