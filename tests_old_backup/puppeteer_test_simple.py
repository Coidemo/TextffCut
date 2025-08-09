#!/usr/bin/env python3
"""
TextffCut Puppeteer MCPテスト - シンプル版
実際に動作したコマンドを再現可能な形式で記録
"""

import json
from datetime import datetime
from pathlib import Path

# Puppeteer MCPコマンドのテンプレート
PUPPETEER_COMMANDS = {
    "navigate": {
        "description": "アプリケーションを開く",
        "mcp_tool": "mcp__puppeteer__puppeteer_navigate",
        "example": {
            "url": "http://localhost:8501",
            "allowDangerous": True,
            "launchOptions": {"headless": False, "args": ["--no-sandbox", "--disable-setuid-sandbox"]},
        },
    },
    "screenshot": {
        "description": "スクリーンショットを撮影",
        "mcp_tool": "mcp__puppeteer__puppeteer_screenshot",
        "examples": [
            {"name": "01_home", "width": 1280, "height": 800},
            {"name": "02_after_update", "width": 1280, "height": 800},
            {"name": "03_dropdown_opened", "width": 1280, "height": 800},
        ],
    },
    "click_button": {
        "description": "ボタンをクリック（テキストで検索）",
        "mcp_tool": "mcp__puppeteer__puppeteer_evaluate",
        "script": """
const buttons = Array.from(document.querySelectorAll('button'));
const targetButton = buttons.find(btn => btn.textContent.includes('{button_text}'));
if (targetButton) {{
    targetButton.click();
    'Button clicked: {button_text}';
}} else {{
    'Button not found: {button_text}';
}}
""",
    },
    "click_dropdown": {
        "description": "Streamlitのドロップダウンをクリック",
        "mcp_tool": "mcp__puppeteer__puppeteer_evaluate",
        "script": """
const dropdown = document.querySelector('div[data-baseweb="select"]');
if (dropdown) {
    dropdown.click();
    'Dropdown clicked';
} else {
    'No dropdown found';
}
""",
    },
    "input_text": {
        "description": "テキスト入力（React対応）",
        "mcp_tool": "mcp__puppeteer__puppeteer_evaluate",
        "script": """
(() => {{
    const input = document.querySelector('input[type="text"]');
    if (input) {{
        input.focus();
        input.value = '{text}';
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        input.blur();
        return 'Text entered: {text}';
    }}
    return 'No text input found';
}})();
""",
    },
    "get_page_text": {
        "description": "ページのテキストを取得",
        "mcp_tool": "mcp__puppeteer__puppeteer_evaluate",
        "script": "document.body.innerText.substring(0, 500);",
    },
    "scroll_page": {
        "description": "ページをスクロール",
        "mcp_tool": "mcp__puppeteer__puppeteer_evaluate",
        "script": "window.scrollTo(0, {y_position});",
    },
}


def generate_test_sequence():
    """テストシーケンスを生成"""
    return [
        {
            "step": 1,
            "action": "navigate",
            "description": "TextffCutアプリを開く",
            "params": PUPPETEER_COMMANDS["navigate"]["example"],
        },
        {
            "step": 2,
            "action": "screenshot",
            "description": "初期画面のスクリーンショット",
            "params": {"name": "01_home", "width": 1280, "height": 800},
        },
        {"step": 3, "action": "click_button", "description": "更新ボタンをクリック", "params": {"button_text": "更新"}},
        {
            "step": 4,
            "action": "screenshot",
            "description": "更新後のスクリーンショット",
            "params": {"name": "02_after_update", "width": 1280, "height": 800},
        },
        {"step": 5, "action": "click_dropdown", "description": "動画選択ドロップダウンを開く", "params": {}},
        {
            "step": 6,
            "action": "screenshot",
            "description": "ドロップダウン展開のスクリーンショット",
            "params": {"name": "03_dropdown", "width": 1280, "height": 800},
        },
        {
            "step": 7,
            "action": "input_text",
            "description": "動画パスを入力",
            "params": {"text": "videos/test_sample_speech.mp4"},
        },
        {"step": 8, "action": "scroll_page", "description": "ページを下にスクロール", "params": {"y_position": 500}},
        {
            "step": 9,
            "action": "screenshot",
            "description": "スクロール後のスクリーンショット",
            "params": {"name": "04_scrolled", "width": 1280, "height": 800},
        },
    ]


def save_test_commands():
    """テストコマンドをファイルに保存"""
    test_sequence = generate_test_sequence()

    # 実行可能なコマンドリストを作成
    executable_commands = []

    for step in test_sequence:
        command_template = PUPPETEER_COMMANDS.get(step["action"])
        if not command_template:
            continue

        command = {
            "step": step["step"],
            "description": step["description"],
            "mcp_tool": command_template["mcp_tool"],
            "params": step["params"],
        }

        # スクリプトがある場合は、パラメータで置換
        if "script" in command_template:
            script = command_template["script"]
            for key, value in step["params"].items():
                script = script.replace(f"{{{key}}}", str(value))
            command["script"] = script

        executable_commands.append(command)

    # ファイルに保存
    output = {
        "generated_at": datetime.now().isoformat(),
        "description": "TextffCut E2Eテスト - 実行可能なPuppeteerコマンド",
        "commands": executable_commands,
        "usage": "各コマンドのmcp_toolを使用して、paramsまたはscriptを実行してください",
    }

    output_path = Path("tests/puppeteer_executable_commands.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 実行可能なコマンドを保存しました: {output_path}")

    # 使用例も表示
    print("\n📝 使用例:")
    print("```")
    for cmd in executable_commands[:3]:  # 最初の3つを例として表示
        print(f"\n# Step {cmd['step']}: {cmd['description']}")
        print(f"await {cmd['mcp_tool']}(")
        if "script" in cmd:
            print(f'    script: `{cmd["script"][:100]}...`')
        else:
            print(f"    {json.dumps(cmd['params'], indent=4)}")
        print(")")
    print("```")


if __name__ == "__main__":
    print("=" * 60)
    print("TextffCut Puppeteer MCPテストコマンド生成")
    print("=" * 60)

    save_test_commands()

    print("\n💡 ヒント:")
    print("  - tests/puppeteer_commands.md で詳細なコマンド説明を確認")
    print("  - tests/puppeteer_executable_commands.json で実行可能なコマンドリストを確認")
    print("  - 実際の実行はClaude経由でMCPツールを呼び出す必要があります")
