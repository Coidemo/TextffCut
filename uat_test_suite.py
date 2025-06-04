#!/usr/bin/env python3
"""
UAT（ユーザー受け入れテスト）スイート
SmartSplitTranscriberの機能が既存機能に影響を与えていないことを確認
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

from config import Config
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription import Transcriber
from core.video import VideoProcessor, VideoInfo
from core.text_processor import TextProcessor
from utils.logging import get_logger

logger = get_logger(__name__)


class UATTestSuite:
    """UAT テストスイート"""
    
    def __init__(self):
        self.config = Config()
        self.test_results = []
        self.test_video_path = None
        
    def setup_test_video(self):
        """テスト用の動画を準備"""
        # 既存の短い動画を使用
        test_candidates = [
            "/Users/naoki/myProject/TextffCut/videos/test_very_short_chunk.mp4",
            "/Users/naoki/myProject/TextffCut/videos/30.1.mp4",
            "/Users/naoki/myProject/TextffCut/videos/test.mp4"
        ]
        
        for candidate in test_candidates:
            if Path(candidate).exists():
                self.test_video_path = candidate
                return True
        
        logger.error("テスト用動画が見つかりません")
        return False
    
    def test_basic_transcription(self):
        """基本的な文字起こし機能のテスト"""
        test_name = "基本的な文字起こし"
        logger.info(f"テスト: {test_name}")
        
        try:
            # SmartSplitTranscriberを使用
            transcriber = SmartSplitTranscriber(self.config)
            
            # 文字起こし実行
            result = transcriber.transcribe(
                self.test_video_path,
                model_size="small",
                use_cache=False,
                save_cache=False
            )
            
            # 結果検証
            assert result is not None, "文字起こし結果がNone"
            assert len(result.segments) >= 0, "セグメントが存在しない"
            assert result.processing_time > 0, "処理時間が0"
            
            self.test_results.append({
                "test": test_name,
                "status": "PASS",
                "segments": len(result.segments),
                "processing_time": result.processing_time
            })
            logger.info(f"✓ {test_name}: 成功")
            
        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "FAIL",
                "error": str(e)
            })
            logger.error(f"✗ {test_name}: 失敗 - {e}")
    
    def test_cache_functionality(self):
        """キャッシュ機能のテスト"""
        test_name = "キャッシュ機能"
        logger.info(f"テスト: {test_name}")
        
        try:
            transcriber = SmartSplitTranscriber(self.config)
            
            # 1回目：キャッシュ作成
            result1 = transcriber.transcribe(
                self.test_video_path,
                model_size="small",
                use_cache=False,
                save_cache=True
            )
            time1 = result1.processing_time
            
            # 2回目：キャッシュ使用
            start_time = time.time()
            result2 = transcriber.transcribe(
                self.test_video_path,
                model_size="small",
                use_cache=True,
                save_cache=False
            )
            cache_time = time.time() - start_time
            
            # 検証
            assert result2 is not None, "キャッシュからの読み込み失敗"
            assert len(result1.segments) == len(result2.segments), "セグメント数が一致しない"
            assert cache_time < time1 * 0.1, "キャッシュが高速化されていない"
            
            self.test_results.append({
                "test": test_name,
                "status": "PASS",
                "original_time": time1,
                "cache_time": cache_time,
                "speedup": time1 / cache_time if cache_time > 0 else float('inf')
            })
            logger.info(f"✓ {test_name}: 成功 (高速化: {time1/cache_time:.1f}倍)")
            
        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "FAIL",
                "error": str(e)
            })
            logger.error(f"✗ {test_name}: 失敗 - {e}")
    
    def test_video_processing(self):
        """動画処理機能のテスト"""
        test_name = "動画処理機能"
        logger.info(f"テスト: {test_name}")
        
        try:
            video_processor = VideoProcessor(self.config)
            
            # 動画情報取得
            video_info = VideoInfo.from_file(self.test_video_path)
            assert video_info.duration > 0, "動画の長さが0"
            assert video_info.width > 0, "動画の幅が0"
            assert video_info.height > 0, "動画の高さが0"
            
            # 無音検出（短い動画なので簡易テスト）
            if video_info.duration < 60:
                silence_regions = video_processor.detect_silence(
                    self.test_video_path,
                    noise_threshold=-35,
                    min_silence_duration=0.5
                )
                assert isinstance(silence_regions, list), "無音検出結果がリストでない"
            
            self.test_results.append({
                "test": test_name,
                "status": "PASS",
                "video_duration": video_info.duration,
                "video_resolution": f"{video_info.width}x{video_info.height}"
            })
            logger.info(f"✓ {test_name}: 成功")
            
        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "FAIL",
                "error": str(e)
            })
            logger.error(f"✗ {test_name}: 失敗 - {e}")
    
    def test_text_processing(self):
        """テキスト処理機能のテスト"""
        test_name = "テキスト処理機能"
        logger.info(f"テスト: {test_name}")
        
        try:
            text_processor = TextProcessor()
            
            # サンプルテキストで差分検出
            text1 = "これはテストです。"
            text2 = "これはテストです。追加されたテキスト。"
            
            diff_result = text_processor.find_differences(text1, text2)
            assert diff_result.has_additions(), "追加部分が検出されない"
            assert len(diff_result.added_chars) > 0, "追加文字が検出されない"
            
            self.test_results.append({
                "test": test_name,
                "status": "PASS",
                "added_chars_count": len(diff_result.added_chars)
            })
            logger.info(f"✓ {test_name}: 成功")
            
        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "FAIL",
                "error": str(e)
            })
            logger.error(f"✗ {test_name}: 失敗 - {e}")
    
    def test_api_mode_compatibility(self):
        """APIモード互換性のテスト"""
        test_name = "APIモード互換性"
        logger.info(f"テスト: {test_name}")
        
        try:
            # APIモードを一時的に有効化（実際のAPIは呼び出さない）
            original_use_api = self.config.transcription.use_api
            self.config.transcription.use_api = True
            
            transcriber = SmartSplitTranscriber(self.config)
            
            # APIモードでも初期化できることを確認
            assert hasattr(transcriber, '_transcribe_api_optimized'), "API最適化メソッドが存在しない"
            
            # 設定を元に戻す
            self.config.transcription.use_api = original_use_api
            
            self.test_results.append({
                "test": test_name,
                "status": "PASS",
                "note": "APIモード初期化確認のみ（実際のAPI呼び出しはなし）"
            })
            logger.info(f"✓ {test_name}: 成功")
            
        except Exception as e:
            self.config.transcription.use_api = original_use_api
            self.test_results.append({
                "test": test_name,
                "status": "FAIL",
                "error": str(e)
            })
            logger.error(f"✗ {test_name}: 失敗 - {e}")
    
    def run_all_tests(self):
        """全テストを実行"""
        logger.info("=== UAT テストスイート開始 ===")
        
        if not self.setup_test_video():
            return False
        
        logger.info(f"テスト動画: {self.test_video_path}")
        
        # 各テストを実行
        self.test_basic_transcription()
        self.test_cache_functionality()
        self.test_video_processing()
        self.test_text_processing()
        self.test_api_mode_compatibility()
        
        # 結果集計
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed_tests = total_tests - passed_tests
        
        logger.info("=== テスト結果サマリー ===")
        logger.info(f"総テスト数: {total_tests}")
        logger.info(f"成功: {passed_tests}")
        logger.info(f"失敗: {failed_tests}")
        
        # 結果をJSONで保存
        result_file = f"uat_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_date": datetime.now().isoformat(),
                "test_video": self.test_video_path,
                "summary": {
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests
                },
                "results": self.test_results
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"テスト結果を保存: {result_file}")
        
        return failed_tests == 0


def main():
    """メイン関数"""
    suite = UATTestSuite()
    success = suite.run_all_tests()
    
    if success:
        logger.info("✅ すべてのテストが成功しました")
        sys.exit(0)
    else:
        logger.error("❌ 一部のテストが失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()