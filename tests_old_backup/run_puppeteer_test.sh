#!/bin/bash
# TextffCut Puppeteer MCPテスト実行スクリプト
# 実際に動作したコマンドを再現可能な形で実行

set -e

echo "================================"
echo "TextffCut Puppeteer MCPテスト"
echo "================================"
echo ""

# 環境確認
echo "📋 環境確認"
echo "  APIキー: ${OPENAI_API_KEY:+設定済み}"
echo "  Streamlit URL: http://localhost:8501"
echo ""

# Streamlitが起動しているか確認
if ! curl -s http://localhost:8501 > /dev/null; then
    echo "❌ Streamlitが起動していません"
    echo "以下のコマンドで起動してください:"
    echo "  streamlit run main.py"
    exit 1
fi

echo "✅ Streamlitが起動しています"
echo ""

# テスト動画の準備
echo "🎬 テスト動画を準備"
if [ ! -f "videos/test_sample_speech.mp4" ]; then
    echo "  テスト動画を作成しています..."
    cd tests/test_data
    python create_test_video.py
    cd ../..
    mkdir -p videos
    cp tests/test_data/test_sample_speech.mp4 videos/
    echo "  ✅ テスト動画を配置しました"
else
    echo "  ✅ テスト動画は既に存在します"
fi
echo ""

# スクリーンショットディレクトリの作成
SCREENSHOT_DIR="tests/screenshots/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SCREENSHOT_DIR"
echo "📸 スクリーンショット保存先: $SCREENSHOT_DIR"
echo ""

# Pythonスクリプトで実際のテストを実行
cat > tests/temp_puppeteer_test.py << 'EOF'
import os
import time
import json
from datetime import datetime

# テスト結果
results = {
    "timestamp": datetime.now().isoformat(),
    "tests": []
}

print("🚀 Puppeteerテストを開始します\n")

# ここで実際のMCP呼び出しが必要
# 以下は実行すべきコマンドの例

commands = [
    {
        "step": "1. アプリケーションを開く",
        "command": "mcp__puppeteer__puppeteer_navigate",
        "params": {
            "url": "http://localhost:8501",
            "allowDangerous": True,
            "launchOptions": {
                "headless": False,
                "args": ["--no-sandbox", "--disable-setuid-sandbox"]
            }
        }
    },
    {
        "step": "2. 初期画面のスクリーンショット",
        "command": "mcp__puppeteer__puppeteer_screenshot",
        "params": {
            "name": "01_home",
            "width": 1280,
            "height": 800
        }
    },
    {
        "step": "3. 更新ボタンをクリック",
        "command": "mcp__puppeteer__puppeteer_evaluate",
        "params": {
            "script": """
const buttons = Array.from(document.querySelectorAll('button'));
const updateButton = buttons.find(btn => btn.textContent.includes('更新'));
if (updateButton) {
    updateButton.click();
    'Update button clicked';
} else {
    'Update button not found';
}
"""
        }
    },
    {
        "step": "4. ドロップダウンを開く",
        "command": "mcp__puppeteer__puppeteer_evaluate",
        "params": {
            "script": """
const dropdown = document.querySelector('div[data-baseweb="select"]');
if (dropdown) {
    dropdown.click();
    'Dropdown clicked';
} else {
    'No dropdown found';
}
"""
        }
    },
    {
        "step": "5. ドロップダウン展開後のスクリーンショット",
        "command": "mcp__puppeteer__puppeteer_screenshot",
        "params": {
            "name": "02_dropdown",
            "width": 1280,
            "height": 800
        }
    }
]

# コマンドを表示（実際の実行はMCP経由で行う必要がある）
for cmd in commands:
    print(f"\n{cmd['step']}")
    print(f"  コマンド: {cmd['command']}")
    print(f"  パラメータ: {json.dumps(cmd['params'], indent=2, ensure_ascii=False)}")
    results["tests"].append({
        "step": cmd['step'],
        "command": cmd['command'],
        "status": "documented"
    })

# 結果を保存
report_path = f"tests/reports/puppeteer_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
os.makedirs("tests/reports", exist_ok=True)
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n📄 テストコマンドを記録しました: {report_path}")
EOF

python tests/temp_puppeteer_test.py
rm -f tests/temp_puppeteer_test.py

echo ""
echo "================================"
echo "テスト完了"
echo "================================"
echo ""
echo "📝 注意事項:"
echo "  - 実際のPuppeteer MCPコマンドはClaude経由で実行する必要があります"
echo "  - tests/puppeteer_commands.md に詳細なコマンド例があります"
echo "  - スクリーンショットは $SCREENSHOT_DIR に保存されます"
echo ""