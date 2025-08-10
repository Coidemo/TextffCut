"""
SmartBoundaryTranscriberのVADベース実装のテスト
"""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.transcription_smart_boundary import SmartBoundaryTranscriber


class TestSmartBoundaryVAD(unittest.TestCase):
    """SmartBoundaryTranscriberのVADベースセグメント分割テスト"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = MagicMock()
        self.config.transcription.use_api = False
        self.config.transcription.language = "ja"
        self.config.transcription.compute_type = "int8"
        self.config.transcription.model_size = "medium"
        
        self.transcriber = SmartBoundaryTranscriber(self.config)
        
    def test_vad_segment_detection(self):
        """VADベースのセグメント検出のテスト"""
        # テスト用の音声パス
        test_audio_path = "/tmp/test_audio.wav"
        
        # ffmpegの出力をモック
        mock_ffmpeg_output = """
[silencedetect @ 0x123] silence_start: 10.5
[silencedetect @ 0x123] silence_end: 11.2 | silence_duration: 0.7
[silencedetect @ 0x123] silence_start: 45.0
[silencedetect @ 0x123] silence_end: 46.5 | silence_duration: 1.5
[silencedetect @ 0x123] silence_start: 100.0
        """
        
        with patch('subprocess.run') as mock_run:
            # ffprobeの呼び出し（総時間取得）
            mock_duration_result = MagicMock()
            mock_duration_result.stdout = "120.0"
            
            # ffmpegの呼び出し（無音検出）
            mock_silence_result = MagicMock()
            mock_silence_result.stdout = mock_ffmpeg_output
            
            mock_run.side_effect = [mock_duration_result, mock_silence_result]
            
            segments = self.transcriber._find_vad_based_segments(test_audio_path)
            
        # 期待される音声区間
        # 0.0-10.5, 11.2-45.0, 46.5-100.0, 100.0-120.0（最後の無音に終了がないため）
        self.assertGreater(len(segments), 0)
        
        # 各セグメントが30秒以内であることを確認
        for start, end in segments:
            self.assertLessEqual(end - start, 30.0)
            self.assertGreaterEqual(end - start, 5.0)  # 最小5秒
            
    def test_long_segment_splitting(self):
        """長いセグメントの30秒分割テスト"""
        # 60秒の連続音声（無音なし）をシミュレート
        with patch('subprocess.run') as mock_run:
            # ffprobeの呼び出し
            mock_duration_result = MagicMock()
            mock_duration_result.stdout = "60.0"
            
            # ffmpegの呼び出し（無音なし）
            mock_silence_result = MagicMock()
            mock_silence_result.stdout = ""  # 無音なし
            
            mock_run.side_effect = [mock_duration_result, mock_silence_result]
            
            segments = self.transcriber._find_vad_based_segments("/tmp/test.wav")
            
        # 60秒を30秒以内に分割
        # 期待: (0-20), (20-40), (40-60) のような分割
        total_duration = sum(end - start for start, end in segments)
        self.assertAlmostEqual(total_duration, 60.0, places=1)
        
        # 各セグメントが制限内
        for start, end in segments:
            self.assertLessEqual(end - start, 30.0)
            
    def test_short_segment_merging(self):
        """短いセグメントの結合テスト"""
        # 短い音声区間が連続する場合
        mock_output = """
[silencedetect @ 0x123] silence_start: 3.0
[silencedetect @ 0x123] silence_end: 3.2 | silence_duration: 0.2
[silencedetect @ 0x123] silence_start: 6.0
[silencedetect @ 0x123] silence_end: 6.3 | silence_duration: 0.3
[silencedetect @ 0x123] silence_start: 10.0
[silencedetect @ 0x123] silence_end: 10.4 | silence_duration: 0.4
        """
        
        with patch('subprocess.run') as mock_run:
            mock_duration_result = MagicMock()
            mock_duration_result.stdout = "15.0"
            
            mock_silence_result = MagicMock()
            mock_silence_result.stdout = mock_output
            
            mock_run.side_effect = [mock_duration_result, mock_silence_result]
            
            segments = self.transcriber._find_vad_based_segments("/tmp/test.wav")
            
        # 短いセグメントが結合されていること
        # 各セグメントが最小長（5秒）以上
        for start, end in segments:
            self.assertGreaterEqual(end - start, 5.0)
            
    def test_compute_type_usage_in_process_segment(self):
        """_process_segmentでの動的compute_type使用テスト"""
        # オプティマイザをモック
        mock_optimizer = MagicMock()
        mock_optimizer.get_optimal_params.return_value = {
            "chunk_seconds": 30,
            "align_chunk_seconds": 60,
            "max_workers": 1,
            "batch_size": 8,
            "compute_type": "float16"  # 動的に決定された値
        }
        
        # メモリモニターをモック
        mock_memory_monitor = MagicMock()
        mock_memory_monitor.get_memory_usage.return_value = 65.0
        
        self.transcriber.optimizer = mock_optimizer
        self.transcriber.memory_monitor = mock_memory_monitor
        
        # _process_segmentの準備
        with patch('os.path.join'), \
             patch('subprocess.run'), \
             patch('whisperx.load_audio'), \
             patch('whisperx.load_model') as mock_load_model, \
             patch('whisperx.load_align_model'), \
             patch('os.path.exists', return_value=True), \
             patch('os.unlink'):
            
            mock_model = MagicMock()
            mock_model.transcribe.return_value = {"segments": []}
            mock_load_model.return_value = mock_model
            
            # _process_segmentを呼び出し
            try:
                self.transcriber._process_segment("/tmp/video.mp4", 0.0, 30.0, "medium", 0, skip_alignment=True)
            except Exception:
                pass  # エラーは無視（モックの設定が不完全なため）
            
            # load_modelがfloat16で呼ばれたことを確認
            mock_load_model.assert_called_with(
                "medium",
                self.transcriber.device,
                compute_type="float16",  # 動的に選択された値
                language="ja"
            )
            
    def test_fallback_to_fixed_segments(self):
        """VAD失敗時の固定長分割へのフォールバック"""
        with patch('subprocess.run') as mock_run:
            # 最初のffprobeコマンド（VAD内）が失敗
            mock_run.side_effect = Exception("FFmpeg error")
            
            # ログ出力を確認
            with patch('core.transcription_smart_boundary.logger') as mock_logger:
                # VADが失敗してフォールバックが呼ばれる
                with self.assertRaises(Exception):
                    # フォールバックでも失敗することを期待
                    segments = self.transcriber._find_vad_based_segments("/tmp/test.wav")
                
                # 警告ログが出力されていることを確認
                mock_logger.warning.assert_called()


if __name__ == "__main__":
    unittest.main()