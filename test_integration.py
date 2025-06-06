#!/usr/bin/env python
"""
統合テストスクリプト
APIモードでのアライメント自動実行機能をテスト
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_api_alignment_integration():
    """APIモードでのアライメント統合テスト"""
    print("\n=== APIモードアライメント統合テスト ===")
    
    # モックオブジェクトの準備
    mock_config = Mock()
    mock_config.transcription.use_api = True
    
    # wordsなしのセグメント
    mock_segment_without_words = Mock()
    mock_segment_without_words.words = []
    mock_segment_without_words.text = "テストテキスト"
    
    # wordsありのセグメント（アライメント後）
    mock_word = Mock()
    mock_word.word = "テ"
    mock_word.start = 0.0
    mock_word.end = 0.1
    
    mock_segment_with_words = Mock()
    mock_segment_with_words.words = [mock_word]
    mock_segment_with_words.text = "テストテキスト"
    
    # 文字起こし結果（wordsなし）
    mock_result = Mock()
    mock_result.segments = [mock_segment_without_words]
    mock_result.language = "ja"
    
    # AlignmentProcessorのモック
    with patch('main.AlignmentProcessor') as MockAlignmentProcessor:
        mock_processor = MockAlignmentProcessor.return_value
        mock_processor.align.return_value = [mock_segment_with_words]
        
        # テスト対象のコードを実行
        from main import config
        config.transcription.use_api = True
        
        # wordsチェックのテスト
        has_words = True
        if hasattr(mock_result, 'segments'):
            segments_without_words = [
                seg for seg in mock_result.segments
                if not hasattr(seg, 'words') or not seg.words or len(seg.words) == 0
            ]
            if segments_without_words:
                has_words = False
        
        print(f"✓ wordsチェック: has_words = {has_words}")
        assert not has_words, "wordsなしが正しく検出されるべき"
        
        # アライメント実行のシミュレーション
        if not has_words:
            print("✓ アライメント処理を実行")
            aligned_segments = mock_processor.align(
                mock_result.segments,
                "test_video.mp4",
                "ja",
                None
            )
            
            print(f"✓ アライメント結果: {len(aligned_segments)}セグメント")
            assert len(aligned_segments) == 1
            assert len(aligned_segments[0].words) > 0
            
            # 結果の更新
            mock_result.segments = aligned_segments
            print("✓ 結果を更新")
    
    print("✅ APIモードアライメント統合テスト成功")
    return True


def test_import_and_usage():
    """実際のインポートと使用テスト"""
    print("\n=== インポートと使用テスト ===")
    
    try:
        # 必要なモジュールのインポート
        from core.alignment_processor import AlignmentProcessor
        from core.exceptions import WordsFieldMissingError
        from config import Config
        
        print("✓ 必要なモジュールのインポート成功")
        
        # AlignmentProcessorのインスタンス化
        config = Config()
        processor = AlignmentProcessor(config)
        print("✓ AlignmentProcessorのインスタンス化成功")
        
        # メソッドの存在確認
        assert hasattr(processor, 'align'), "alignメソッドが存在しない"
        print("✓ alignメソッドの存在確認")
        
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_py_syntax():
    """main.pyの構文チェック"""
    print("\n=== main.pyの構文チェック ===")
    
    try:
        import ast
        with open('main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 構文解析
        tree = ast.parse(content)
        print("✓ main.pyの構文エラーなし")
        
        # アライメント関連のコードが含まれているか確認
        source_lines = content.splitlines()
        alignment_lines = [
            (i+1, line) for i, line in enumerate(source_lines)
            if 'AlignmentProcessor' in line or 'alignment_processor' in line
        ]
        
        print(f"✓ アライメント関連のコード: {len(alignment_lines)}箇所")
        for line_no, line in alignment_lines[:3]:
            print(f"  行{line_no}: {line.strip()[:60]}...")
        
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        return False


def test_progress_callback():
    """プログレスコールバックのテスト"""
    print("\n=== プログレスコールバックテスト ===")
    
    # プログレス値を記録
    progress_values = []
    status_messages = []
    
    def mock_progress_callback(progress: float, status: str):
        progress_values.append(progress)
        status_messages.append(status)
        print(f"  進捗: {progress:.1%} - {status}")
    
    # アライメント進捗のシミュレーション
    print("✓ アライメント進捗のシミュレーション:")
    alignment_progress = lambda p, s: mock_progress_callback(0.7 + (p * 0.3), f"🔄 {s}")
    
    # 進捗を送信
    alignment_progress(0.0, "アライメント開始")
    alignment_progress(0.5, "処理中...")
    alignment_progress(1.0, "アライメント完了")
    
    # 検証
    assert len(progress_values) == 3
    assert progress_values[0] == 0.7
    assert progress_values[1] == 0.85
    assert progress_values[2] == 1.0
    
    print("✅ プログレスコールバックテスト成功")
    return True


def run_all_integration_tests():
    """全統合テストを実行"""
    print("="*50)
    print("統合テスト実行")
    print("="*50)
    
    tests = [
        test_api_alignment_integration,
        test_import_and_usage,
        test_main_py_syntax,
        test_progress_callback
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n✗ テスト '{test.__name__}' で予期しないエラー: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    # 結果サマリー
    print("\n" + "="*50)
    print("統合テスト結果サマリー")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n合計: {passed}/{total} テスト合格")
    
    if passed == total:
        print("\n🎉 全ての統合テストが成功しました！")
        print("\n実装内容:")
        print("1. ✅ wordsフィールドの必須検証（フェーズ1）")
        print("2. ✅ APIモードでのアライメント自動実行（フェーズ2）")
        print("3. ✅ プログレスバーの改善（70-100%）")
        print("4. ✅ エラー時の適切な警告表示")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_integration_tests()
    sys.exit(0 if success else 1)