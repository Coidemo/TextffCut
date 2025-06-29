"""
OptimizedTranscriberの単体テスト
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.transcription import TranscriptionResult, TranscriptionSegment
from core.transcription_optimized import OptimizedTranscriber


class TestOptimizedTranscriber(unittest.TestCase):
    """OptimizedTranscriberのテストクラス"""

    def setUp(self):
        """テストの初期設定"""
        self.config = Mock()
        self.config.transcription.use_api = False
        self.config.transcription.language = "ja"
        self.config.transcription.model_size = "base"
        self.config.transcription.compute_type = "int8"
        self.config.transcription.batch_size = 16
        self.config.transcription.chunk_seconds = 30
        self.config.transcription.sample_rate = 16000

    def test_memory_management(self):
        """メモリ管理機能のテスト"""
        transcriber = OptimizedTranscriber(self.config)

        # メモリクリーンアップのテスト
        with patch("gc.collect") as mock_gc:
            transcriber._cleanup_memory(force=True)
            mock_gc.assert_called()

        # メモリ状態表示は例外を起こさないことを確認
        try:
            transcriber._show_memory_status("テスト")
        except Exception as e:
            self.fail(f"_show_memory_status should not raise exception: {e}")

    @patch("core.transcription_optimized.AudioSplitter")
    def test_process_api_chunk(self, mock_audio_splitter):
        """APIチャンク処理のテスト"""
        self.config.transcription.use_api = True
        self.config.transcription.api_key = "test-key"
        self.config.transcription.api_provider = "openai"

        transcriber = OptimizedTranscriber(self.config)

        # APIトランスクライバーのモック
        api_transcriber = Mock()
        api_transcriber.api_config.api_key = "test-key"
        api_transcriber.api_config.language = "ja"

        # 音声データ
        chunk_audio = np.zeros(16000 * 10)  # 10秒
        chunk_start = 0.0
        sample_rate = 16000

        # OpenAIクライアントのモック
        with patch("openai.OpenAI") as mock_openai_class:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.segments = [
                Mock(start=0.0, end=2.0, text="テスト1"),
                Mock(start=2.0, end=4.0, text="テスト2"),
            ]
            mock_client.audio.transcriptions.create.return_value = mock_response
            mock_openai_class.return_value = mock_client

            # テスト実行
            segments = transcriber._process_api_chunk(api_transcriber, chunk_audio, chunk_start, sample_rate)

            # 検証
            self.assertEqual(len(segments), 2)
            self.assertEqual(segments[0].text, "テスト1")
            self.assertEqual(segments[1].text, "テスト2")

    @patch("whisperx.align")
    @patch("whisperx.load_align_model")
    @patch("core.transcription_optimized.AudioSplitter")
    def test_perform_alignment_optimized(self, mock_audio_splitter, mock_load_align, mock_align):
        """最適化されたアライメント処理のテスト"""
        transcriber = OptimizedTranscriber(self.config)

        # アライメントモデルのモック
        mock_load_align.return_value = (Mock(), Mock())

        # 入力セグメント（30分分をシミュレート）
        segments = []
        for i in range(60):  # 30秒×60 = 30分
            segments.append(TranscriptionSegment(start=i * 30, end=(i + 1) * 30, text=f"セグメント{i}", words=None))

        # アライメント結果のモック
        mock_align.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 30.0,
                    "text": "アライメント済み",
                    "words": [{"word": "テスト", "start": 0.0, "end": 1.0}],
                }
            ]
        }

        # 音声データ
        audio = np.zeros(16000 * 1800)  # 30分
        sample_rate = 16000

        # テスト実行
        aligned_segments = transcriber._perform_alignment_optimized(audio, segments, sample_rate)

        # 検証
        self.assertGreater(len(aligned_segments), 0)
        # 20分ごとにグループ化されることを確認（30分なので2グループ）
        self.assertEqual(mock_align.call_count, 2)

    @patch("whisperx.load_audio")
    def test_transcribe_api_optimized_with_cache(self, mock_load_audio):
        """APIモードのキャッシュ処理テスト"""
        self.config.transcription.use_api = True
        self.config.transcription.api_key = "test-key"

        transcriber = OptimizedTranscriber(self.config)

        # キャッシュのモック
        cached_result = TranscriptionResult(
            language="ja",
            segments=[TranscriptionSegment(0, 10, "キャッシュから")],
            original_audio_path="test.mp4",
            model_size="base",
            processing_time=1.0,
        )

        with patch.object(transcriber, "load_from_cache", return_value=cached_result) as mock_load:
            # テスト実行
            result = transcriber.transcribe("test.mp4", model_size="base", use_cache=True)

            # 検証
            mock_load.assert_called_once()
            self.assertEqual(result.segments[0].text, "キャッシュから")

    @patch("whisperx.load_model")
    @patch("whisperx.load_align_model")
    @patch("whisperx.load_audio")
    @patch("whisperx.align")
    @patch("core.transcription_optimized.AudioSplitter")
    def test_transcribe_local_optimized(
        self, mock_audio_splitter, mock_align, mock_load_audio, mock_load_align_model, mock_load_model
    ):
        """ローカルモードの最適化された文字起こしテスト"""
        # AudioSplitterのモックを先に設定
        mock_splitter_instance = Mock()
        mock_audio_splitter.return_value = mock_splitter_instance

        # OptimizedTranscriberを初期化（この時点でAudioSplitterがモックに置き換わる）
        transcriber = OptimizedTranscriber(self.config)

        # 音声データのモック
        audio_data = np.zeros(16000 * 60)  # 1分
        mock_load_audio.return_value = audio_data

        # モデルのモック
        mock_asr_model = Mock()
        mock_asr_model.transcribe.return_value = {"segments": [{"start": 0.0, "end": 10.0, "text": "テスト"}]}
        mock_load_model.return_value = mock_asr_model

        # アライメントモデルのモック
        mock_load_align_model.return_value = (Mock(), Mock())
        mock_align.return_value = {"segments": [{"start": 0.0, "end": 10.0, "text": "アライメント済み"}]}

        # split_audio_arrayのモック設定
        mock_splitter_instance.split_audio_array.return_value = [(audio_data, 0.0, 60.0)]  # 1つのチャンク

        # テスト実行
        result = transcriber._transcribe_local_optimized(
            "test.mp4", model_size="base", use_cache=False, save_cache=False
        )

        # 検証
        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(result.language, "ja")
        # セグメントはアライメント結果から来るはず
        self.assertGreater(len(result.segments), 0)
        self.assertEqual(result.segments[0].text, "アライメント済み")

        # split_audio_arrayが正しいパラメータで呼ばれたことを確認
        mock_splitter_instance.split_audio_array.assert_called_once()
        call_args = mock_splitter_instance.split_audio_array.call_args
        self.assertEqual(call_args[0][1], 16000)  # sample_rate
        self.assertEqual(call_args[1]["target_duration"], 1200.0)  # 20分

    @patch("whisperx.load_audio")
    def test_error_fallback(self, mock_load_audio):
        """エラー時のフォールバック機能テスト"""
        transcriber = OptimizedTranscriber(self.config)

        # load_audioでエラーを発生させる
        mock_load_audio.side_effect = FileNotFoundError("ファイルが見つかりません")

        # テスト実行 - エラーが伝播されることを確認
        with self.assertRaises(FileNotFoundError):
            transcriber.transcribe("test.mp4", model_size="base")


if __name__ == "__main__":
    unittest.main()
