"""
Phase 2機能のテスト
キーボードショートカットとインタラクティブ操作
"""

import unittest
from unittest.mock import Mock

from core.waveform_processor import WaveformData
from ui.keyboard_handler import KeyboardShortcuts
from ui.waveform_interaction import WaveformInteraction, WaveformPlayback


class TestKeyboardHandler(unittest.TestCase):
    """キーボードハンドラーのテスト"""

    def setUp(self):
        self.keyboard = KeyboardShortcuts()
        self.mock_handler = Mock()

    def test_register_handler(self):
        """ハンドラー登録のテスト"""
        self.keyboard.register_handler("test_action", self.mock_handler)
        self.assertIn("test_action", self.keyboard.action_handlers)
        self.assertEqual(self.keyboard.action_handlers["test_action"], self.mock_handler)

    def test_handle_space_key(self):
        """スペースキーのハンドリング"""
        self.keyboard.register_handler("toggle_playback", self.mock_handler)

        key_event = {"key": "space", "ctrlKey": False, "shiftKey": False, "altKey": False, "metaKey": False}

        result = self.keyboard.handle_key_event(key_event)
        self.assertTrue(result)
        self.mock_handler.assert_called_once()

    def test_handle_arrow_with_shift(self):
        """Shift+矢印キーのハンドリング"""
        self.keyboard.register_handler("adjust_start_time", self.mock_handler)

        key_event = {"key": "arrowleft", "ctrlKey": False, "shiftKey": True, "altKey": False, "metaKey": False}

        result = self.keyboard.handle_key_event(key_event)
        self.assertTrue(result)
        self.mock_handler.assert_called_once_with(-0.1)

    def test_handle_ctrl_z(self):
        """Ctrl+Zのハンドリング"""
        self.keyboard.register_handler("undo", self.mock_handler)

        key_event = {"key": "z", "ctrlKey": True, "shiftKey": False, "altKey": False, "metaKey": False}

        result = self.keyboard.handle_key_event(key_event)
        self.assertTrue(result)
        self.mock_handler.assert_called_once()

    def test_disabled_keyboard(self):
        """無効化されたキーボードのテスト"""
        self.keyboard.register_handler("test_action", self.mock_handler)
        self.keyboard.disable()

        key_event = {"key": "space"}
        result = self.keyboard.handle_key_event(key_event)

        self.assertFalse(result)
        self.mock_handler.assert_not_called()

    def test_get_help_text(self):
        """ヘルプテキスト生成のテスト"""
        help_text = self.keyboard.get_help_text()

        self.assertIn("キーボードショートカット", help_text)
        self.assertIn("SPACE", help_text)
        self.assertIn("再生/停止", help_text)


class TestWaveformInteraction(unittest.TestCase):
    """波形インタラクションのテスト"""

    def setUp(self):
        self.interaction = WaveformInteraction()
        self.waveform_data = WaveformData(
            segment_id="test", sample_rate=44100, samples=[0.5] * 100, duration=5.0, start_time=0.0, end_time=5.0
        )

    def test_process_click_near_boundary(self):
        """境界付近のクリック処理"""
        click_data = {"points": [{"x": 2.05, "y": 0.5}]}  # 境界（2.0）の近く

        boundaries = [2.0, 4.0]

        result = self.interaction.process_click_event(click_data, self.waveform_data, boundaries)

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "adjust_boundary")
        self.assertEqual(result["boundary_time"], 2.0)
        self.assertAlmostEqual(result["distance"], 0.05, places=2)

    def test_process_normal_click(self):
        """通常のクリック処理"""
        click_data = {"points": [{"x": 3.0, "y": 0.5}]}  # 境界から離れた位置

        boundaries = [2.0, 4.0]

        result = self.interaction.process_click_event(click_data, self.waveform_data, boundaries)

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "select_time")
        self.assertEqual(result["time"], 3.0)
        self.assertEqual(result["amplitude"], 0.5)

    def test_find_nearest_boundary(self):
        """最も近い境界の検出"""
        boundaries = [1.0, 2.5, 4.0]

        # 2.5に最も近い
        nearest = self.interaction._find_nearest_boundary(2.4, boundaries)
        self.assertEqual(nearest, 2.5)

        # 1.0に最も近い
        nearest = self.interaction._find_nearest_boundary(0.8, boundaries)
        self.assertEqual(nearest, 1.0)

        # 空のリスト
        nearest = self.interaction._find_nearest_boundary(2.0, [])
        self.assertIsNone(nearest)

    def test_interactive_config(self):
        """インタラクティブ設定の生成"""
        config = self.interaction.create_interactive_waveform_config()

        self.assertIsInstance(config, dict)
        self.assertIn("displayModeBar", config)
        self.assertTrue(config["displayModeBar"])
        self.assertFalse(config["displaylogo"])
        self.assertIn("modeBarButtonsToRemove", config)


class TestWaveformPlayback(unittest.TestCase):
    """波形再生制御のテスト"""

    def setUp(self):
        self.playback = WaveformPlayback()

    def test_initial_state(self):
        """初期状態のテスト"""
        self.assertFalse(self.playback.is_playing)
        self.assertEqual(self.playback.current_position, 0.0)
        self.assertEqual(self.playback.playback_speed, 1.0)

    def test_playback_state_changes(self):
        """再生状態の変更"""
        # 再生開始
        self.playback.is_playing = True
        self.assertTrue(self.playback.is_playing)

        # 位置更新
        self.playback.current_position = 2.5
        self.assertEqual(self.playback.current_position, 2.5)

        # 速度変更
        self.playback.playback_speed = 1.5
        self.assertEqual(self.playback.playback_speed, 1.5)

        # 停止
        self.playback.is_playing = False
        self.playback.current_position = 0.0
        self.assertFalse(self.playback.is_playing)
        self.assertEqual(self.playback.current_position, 0.0)


class TestIntegration(unittest.TestCase):
    """統合テスト"""

    def test_keyboard_interaction_integration(self):
        """キーボードとインタラクションの統合"""
        keyboard = KeyboardShortcuts()
        interaction = WaveformInteraction()
        playback = WaveformPlayback()

        # 再生トグルのハンドラー
        def toggle_playback():
            playback.is_playing = not playback.is_playing

        keyboard.register_handler("toggle_playback", toggle_playback)

        # スペースキーで再生開始
        key_event = {"key": "space"}
        keyboard.handle_key_event(key_event)
        self.assertTrue(playback.is_playing)

        # もう一度スペースキーで停止
        keyboard.handle_key_event(key_event)
        self.assertFalse(playback.is_playing)


if __name__ == "__main__":
    unittest.main()
