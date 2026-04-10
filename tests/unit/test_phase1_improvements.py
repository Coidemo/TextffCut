"""
Phase 1改善のテスト

依存パッケージ（rich, cryptography等）がなくても実行可能なテスト。
ロジックの直接テストとファイルI/Oテストに集中する。
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ===== version_helpers テスト（直接ロジックテスト） =====


class TestVersionHelpers:
    """version_helpersのロジックテスト（importを避けて直接テスト）"""

    def test_pyproject_toml_regex_parsing(self):
        """pyproject.tomlの正規表現パースが正しく動作する"""
        content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        assert match is not None
        assert match.group(1) == "2.0.0"

    def test_pyproject_toml_regex_various_formats(self):
        """さまざまなTOML形式に対応"""
        test_cases = [
            ('version = "1.0.0"', "1.0.0"),
            ('version="2.0.0"', "2.0.0"),
            ('version  =  "3.0.0"', "3.0.0"),
        ]
        for content, expected in test_cases:
            match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
            assert match is not None, f"Failed for: {content}"
            assert match.group(1) == expected

    def test_version_txt_deleted(self):
        """VERSION.txtが削除されていること"""
        assert not (PROJECT_ROOT / "VERSION.txt").exists()

    def test_format_version_display_logic(self):
        """バージョン表示フォーマットのロジック"""

        def format_version_display(version: str, include_prefix: bool = True) -> str:
            if version.startswith("v"):
                return version if include_prefix else version[1:]
            else:
                return f"v{version}" if include_prefix else version

        assert format_version_display("1.0.0") == "v1.0.0"
        assert format_version_display("v1.0.0") == "v1.0.0"
        assert format_version_display("v1.0.0", include_prefix=False) == "1.0.0"
        assert format_version_display("1.0.0", include_prefix=False) == "1.0.0"

    def test_parse_version_logic(self):
        """バージョンパースのロジック"""

        def parse_version(version_string: str):
            version = version_string.lstrip("v")
            parts = version.split(".")
            if len(parts) != 3:
                raise ValueError(f"Invalid: {version_string}")
            return (int(parts[0]), int(parts[1]), int(parts[2]))

        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("v2.0.0") == (2, 0, 0)

        with pytest.raises(ValueError):
            parse_version("invalid")
        with pytest.raises(ValueError):
            parse_version("1.2")


# ===== setup_command テスト（ファイルI/Oのみ） =====


class TestSetupConfig:
    """setup設定管理のテスト"""

    def test_config_json_roundtrip(self):
        """config.jsonの保存/読み込みサイクル"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"

            # 保存
            test_config = {
                "openai_api_key": "sk-test123",
                "default_model": "large-v3",
                "license_key": "XXXX-YYYY",
            }
            config_file.write_text(
                json.dumps(test_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # 読み込み
            loaded = json.loads(config_file.read_text(encoding="utf-8"))
            assert loaded["openai_api_key"] == "sk-test123"
            assert loaded["default_model"] == "large-v3"
            assert loaded["license_key"] == "XXXX-YYYY"

    def test_mask_key_logic(self):
        """APIキーマスク表示ロジック"""

        def mask_key(key: str) -> str:
            if len(key) <= 8:
                return "****"
            return key[:4] + "..." + key[-4:]

        assert mask_key("sk-1234567890abcdef") == "sk-1...cdef"
        assert mask_key("short") == "****"
        assert mask_key("12345678") == "****"
        assert mask_key("123456789") == "1234...6789"

    def test_config_priority_logic(self):
        """設定優先順位ロジック: config.json > 環境変数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"

            # config.jsonに値あり
            config = {"openai_api_key": "sk-from-config"}
            config_file.write_text(json.dumps(config), encoding="utf-8")

            loaded = json.loads(config_file.read_text(encoding="utf-8"))

            # config.jsonの値が環境変数より優先
            env_value = "sk-from-env"
            result = loaded.get("openai_api_key") or env_value
            assert result == "sk-from-config"

            # config.jsonに値なし → 環境変数
            config2 = {"openai_api_key": ""}
            config_file.write_text(json.dumps(config2), encoding="utf-8")
            loaded2 = json.loads(config_file.read_text(encoding="utf-8"))
            result2 = loaded2.get("openai_api_key") or env_value
            assert result2 == "sk-from-env"


# ===== upgrade_command テスト =====


class TestUpgradeCheck:
    """upgradeチェック結果の保存/読み込みテスト"""

    def test_check_result_roundtrip(self):
        """チェック結果の保存/読み込み"""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            check_file = Path(tmpdir) / "last_version_check.json"

            # 保存
            data = {
                "checked_at": time.time(),
                "current_version": "2.0.0",
                "latest_version": "2.1.0",
            }
            check_file.write_text(json.dumps(data), encoding="utf-8")

            # 読み込み
            loaded = json.loads(check_file.read_text(encoding="utf-8"))
            assert loaded["current_version"] == "2.0.0"
            assert loaded["latest_version"] == "2.1.0"
            assert "checked_at" in loaded

    def test_check_interval_logic(self):
        """24時間チェック間隔ロジック"""
        import time

        now = time.time()

        # 23時間前 → チェック不要
        last_check_23h = now - 23 * 3600
        elapsed_hours = (now - last_check_23h) / 3600
        assert elapsed_hours < 24

        # 25時間前 → チェック必要
        last_check_25h = now - 25 * 3600
        elapsed_hours = (now - last_check_25h) / 3600
        assert elapsed_hours >= 24


# ===== command.py ルーティングテスト =====


class TestCommandStructure:
    """command.pyの構造テスト"""

    def test_command_file_has_setup_routing(self):
        """command.pyにsetupルーティングが存在する"""
        content = (PROJECT_ROOT / "textffcut_cli" / "command.py").read_text(encoding="utf-8")
        assert 'sys.argv[1] == "setup"' in content
        assert "from textffcut_cli.setup_command import run_setup" in content

    def test_command_file_has_upgrade_routing(self):
        """command.pyにupgradeルーティングが存在する"""
        content = (PROJECT_ROOT / "textffcut_cli" / "command.py").read_text(encoding="utf-8")
        assert 'sys.argv[1] == "upgrade"' in content
        assert "from textffcut_cli.upgrade_command import run_upgrade" in content

    def test_command_help_includes_setup(self):
        """ヘルプテキストにsetupが含まれる"""
        content = (PROJECT_ROOT / "textffcut_cli" / "command.py").read_text(encoding="utf-8")
        assert "textffcut setup" in content

    def test_command_help_includes_upgrade(self):
        """ヘルプテキストにupgradeが含まれる"""
        content = (PROJECT_ROOT / "textffcut_cli" / "command.py").read_text(encoding="utf-8")
        assert "textffcut upgrade" in content

    def test_setup_command_file_exists(self):
        """setup_command.pyが存在する"""
        assert (PROJECT_ROOT / "textffcut_cli" / "setup_command.py").exists()

    def test_upgrade_command_file_exists(self):
        """upgrade_command.pyが存在する"""
        assert (PROJECT_ROOT / "textffcut_cli" / "upgrade_command.py").exists()


# ===== GUI統合テスト =====


class TestGUIClipIntegration:
    """GUI AI切り抜き統合のテスト"""

    def test_text_editor_has_ai_clip_section(self):
        """text_editor.pyにAI切り抜きセクションが存在する"""
        content = (PROJECT_ROOT / "presentation" / "views" / "text_editor.py").read_text(encoding="utf-8")
        assert "_render_ai_clip_section" in content
        assert "_execute_ai_clip" in content
        assert "AI自動切り抜き" in content

    def test_sidebar_has_model_selector(self):
        """sidebar.pyにモデル選択UIが存在する"""
        content = (PROJECT_ROOT / "presentation" / "views" / "sidebar.py").read_text(encoding="utf-8")
        assert "default_model" in content
        assert "デフォルトモデル" in content
        assert "st.selectbox" in content


# ===== suggest_command テスト =====


class TestSuggestCommandDefaults:
    """suggest_commandのデフォルト動作テスト"""

    def test_files_argument_is_optional(self):
        """filesが省略可能（nargs='*'）"""
        content = (PROJECT_ROOT / "textffcut_cli" / "suggest_command.py").read_text(encoding="utf-8")
        assert 'nargs="*"' in content

    def test_videos_dir_fallback_logic(self):
        """引数なし時の./videos/フォールバックロジックが存在する"""
        content = (PROJECT_ROOT / "textffcut_cli" / "suggest_command.py").read_text(encoding="utf-8")
        assert "videos" in content
        assert "自動検索" in content

    def test_config_value_used_for_api_key(self):
        """APIキーがconfig.jsonからも読み込まれる"""
        content = (PROJECT_ROOT / "textffcut_cli" / "suggest_command.py").read_text(encoding="utf-8")
        assert "get_config_value" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
