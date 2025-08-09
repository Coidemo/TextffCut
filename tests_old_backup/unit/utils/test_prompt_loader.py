"""
プロンプトローダーのユニットテスト
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.prompt_loader import PromptLoader


class TestPromptLoader(unittest.TestCase):
    """PromptLoaderのテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        # 一時ディレクトリを作成
        self.temp_dir = tempfile.mkdtemp()
        self.prompts_dir = Path(self.temp_dir) / "prompts"
        self.default_prompts_dir = Path(self.temp_dir) / "default_prompts"
        
    def tearDown(self):
        """テスト後のクリーンアップ"""
        shutil.rmtree(self.temp_dir)
        
    def test_initialization_creates_prompts_directory(self):
        """初期化時にプロンプトディレクトリが作成されることを確認"""
        # プロンプトディレクトリが存在しない状態で初期化
        loader = PromptLoader(self.prompts_dir)
        
        # ディレクトリが作成されたことを確認
        self.assertTrue(self.prompts_dir.exists())
        
    def test_initialization_copies_from_default_prompts(self):
        """デフォルトプロンプトからファイルがコピーされることを確認"""
        # デフォルトプロンプトディレクトリを作成
        self.default_prompts_dir.mkdir(parents=True)
        
        # デフォルトプロンプトファイルを作成
        clip_content = "Default clip suggestions content"
        title_content = "Default title generation content"
        (self.default_prompts_dir / "clip_suggestions.md").write_text(clip_content)
        (self.default_prompts_dir / "title_generation.md").write_text(title_content)
        
        # 環境変数を設定
        with patch.dict(os.environ, {"DEFAULT_PROMPTS_DIR": str(self.default_prompts_dir)}):
            loader = PromptLoader(self.prompts_dir)
            
        # ファイルがコピーされたことを確認
        self.assertTrue((self.prompts_dir / "clip_suggestions.md").exists())
        self.assertTrue((self.prompts_dir / "title_generation.md").exists())
        
        # 内容が正しくコピーされたことを確認
        self.assertEqual(
            (self.prompts_dir / "clip_suggestions.md").read_text(),
            clip_content
        )
        self.assertEqual(
            (self.prompts_dir / "title_generation.md").read_text(),
            title_content
        )
        
    def test_initialization_creates_basic_prompts_when_no_default(self):
        """デフォルトが利用できない場合は基本的なプロンプトが作成されることを確認"""
        # デフォルトプロンプトディレクトリが存在しない状態
        with patch.dict(os.environ, {"DEFAULT_PROMPTS_DIR": str(self.default_prompts_dir)}):
            loader = PromptLoader(self.prompts_dir)
            
        # ファイルが作成されたことを確認
        self.assertTrue((self.prompts_dir / "clip_suggestions.md").exists())
        self.assertTrue((self.prompts_dir / "title_generation.md").exists())
        
        # 基本的な内容が含まれていることを確認
        clip_content = (self.prompts_dir / "clip_suggestions.md").read_text()
        self.assertIn("{TRANSCRIPTION}", clip_content)
        self.assertIn("バズクリップ候補生成", clip_content)
        
        title_content = (self.prompts_dir / "title_generation.md").read_text()
        self.assertIn("{EDITED_TEXT}", title_content)
        self.assertIn("タイトル生成", title_content)
        
    def test_initialization_is_only_done_once(self):
        """初期化が一度だけ実行されることを確認"""
        # 最初の初期化でファイルを作成
        loader = PromptLoader(self.prompts_dir)
        
        # ファイルの内容を変更
        custom_content = "Custom content"
        (self.prompts_dir / "clip_suggestions.md").write_text(custom_content)
        
        # 同じインスタンスでメソッドを複数回呼び出し
        segments = [{"start": 0.0, "end": 1.0, "text": "Test"}]
        loader.load_buzz_clip_prompt(segments)
        loader.load_buzz_clip_prompt(segments)
        
        # ファイルの内容が変更されていないことを確認（再初期化されていない）
        self.assertEqual(
            (self.prompts_dir / "clip_suggestions.md").read_text(),
            custom_content
        )
        
    def test_load_buzz_clip_prompt(self):
        """バズクリップ用プロンプトの読み込みと変換を確認"""
        # プロンプトファイルを作成
        self.prompts_dir.mkdir(parents=True)
        template = "Template with {TRANSCRIPTION} placeholder"
        (self.prompts_dir / "clip_suggestions.md").write_text(template)
        
        loader = PromptLoader(self.prompts_dir)
        
        # セグメントデータ
        segments = [
            {"start": 0.0, "end": 1.5, "text": "Hello"},
            {"start": 1.5, "end": 3.0, "text": "World"}
        ]
        
        # プロンプトを生成
        result = loader.load_buzz_clip_prompt(segments)
        
        # 期待される結果
        expected = "Template with [0.0s - 1.5s] Hello\n[1.5s - 3.0s] World placeholder"
        self.assertEqual(result, expected)
        
    def test_load_title_generation_prompt(self):
        """タイトル生成用プロンプトの読み込みと変換を確認"""
        # プロンプトファイルを作成
        self.prompts_dir.mkdir(parents=True)
        template = "Generate title for: {EDITED_TEXT}"
        (self.prompts_dir / "title_generation.md").write_text(template)
        
        loader = PromptLoader(self.prompts_dir)
        
        # 編集テキスト
        edited_text = "This is the edited content"
        
        # プロンプトを生成
        result = loader.load_title_generation_prompt(edited_text)
        
        # 期待される結果
        expected = "Generate title for: This is the edited content"
        self.assertEqual(result, expected)
        
    def test_missing_prompt_file_raises_error(self):
        """プロンプトファイルが存在しない場合にエラーが発生することを確認"""
        # 空のディレクトリで初期化（基本ファイルは作成される）
        loader = PromptLoader(self.prompts_dir)
        
        # ファイルを削除
        (self.prompts_dir / "clip_suggestions.md").unlink()
        
        # エラーが発生することを確認
        segments = [{"start": 0.0, "end": 1.0, "text": "Test"}]
        with self.assertRaises(FileNotFoundError):
            loader.load_buzz_clip_prompt(segments)


if __name__ == "__main__":
    unittest.main()