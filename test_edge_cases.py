#!/usr/bin/env python
"""
エッジケーステスト
wordsフィールド検証の境界条件をテスト
"""

import sys
from pathlib import Path
import json

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.models import TranscriptionSegmentV2, TranscriptionResultV2, WordInfo
from core.exceptions import WordsFieldMissingError
from core.transcription import TranscriptionResult, TranscriptionSegment


def test_words_validation():
    """wordsフィールドの検証テスト"""
    print("\n=== wordsフィールド検証テスト ===")
    
    test_cases = [
        {
            "name": "正常なセグメント",
            "segment": TranscriptionSegmentV2(
                id=1,
                start=0.0,
                end=1.0,
                text="こんにちは",
                words=[
                    WordInfo(start=0.0, end=0.2, word="こ"),
                    WordInfo(start=0.2, end=0.4, word="ん"),
                    WordInfo(start=0.4, end=0.6, word="に"),
                    WordInfo(start=0.6, end=0.8, word="ち"),
                    WordInfo(start=0.8, end=1.0, word="は")
                ]
            ),
            "should_pass": True
        },
        {
            "name": "wordsが空のリスト",
            "segment": TranscriptionSegmentV2(
                id=2,
                start=1.0,
                end=2.0,
                text="テスト",
                words=[]
            ),
            "should_pass": False
        },
        {
            "name": "wordsがNone",
            "segment": TranscriptionSegmentV2(
                id=3,
                start=2.0,
                end=3.0,
                text="テスト",
                words=None
            ),
            "should_pass": False
        },
        {
            "name": "一部のwordにタイムスタンプが欠落",
            "segment": TranscriptionSegmentV2(
                id=4,
                start=3.0,
                end=4.0,
                text="あいう",
                words=[
                    WordInfo(start=3.0, end=3.3, word="あ"),
                    WordInfo(start=None, end=None, word="い"),  # タイムスタンプ欠落
                    WordInfo(start=3.6, end=4.0, word="う")
                ]
            ),
            "should_pass": False
        }
    ]
    
    for case in test_cases:
        segment = case["segment"]
        should_pass = case["should_pass"]
        
        # validate_for_search()のテスト
        is_valid, error_msg = segment.validate_for_search()
        
        if should_pass:
            if is_valid:
                print(f"✓ {case['name']}: 正しく検証をパス")
            else:
                print(f"✗ {case['name']}: 誤って検証に失敗 (エラー: {error_msg})")
        else:
            if not is_valid:
                print(f"✓ {case['name']}: 正しく検証エラーを検出 (エラー: {error_msg})")
            else:
                print(f"✗ {case['name']}: 誤って検証をパス")
    
    # TranscriptionResultV2全体の検証
    print("\n--- TranscriptionResultV2の検証 ---")
    
    # 一部のセグメントにwordsが欠落
    result = TranscriptionResultV2(
        segments=[
            TranscriptionSegmentV2(
                id=1,
                start=0.0,
                end=1.0,
                text="正常",
                words=[WordInfo(start=0.0, end=1.0, word="正常")]
            ),
            TranscriptionSegmentV2(
                id=2,
                start=1.0,
                end=2.0,
                text="エラー",
                words=[]  # wordsが空
            )
        ],
        language="ja"
    )
    
    try:
        result.require_valid_words()
        print("✗ エラーが発生すべきなのに発生しなかった")
    except WordsFieldMissingError as e:
        print(f"✓ 正しくWordsFieldMissingErrorが発生")
        print(f"  エラーメッセージ: {e.get_user_message().split()[0]}")
    except Exception as e:
        print(f"✗ 予期しないエラー: {type(e).__name__}: {e}")


def test_v1_to_v2_conversion():
    """V1からV2への変換テスト"""
    print("\n=== V1からV2への変換テスト ===")
    
    # V1形式のデータ（wordsなし）
    v1_result = TranscriptionResult(
        segments=[
            TranscriptionSegment(
                id=1,
                seek=0,
                start=0.0,
                end=1.0,
                text="変換テスト",
                tokens=[1, 2, 3],
                temperature=0.5,
                avg_logprob=-0.5,
                compression_ratio=1.0,
                no_speech_prob=0.1,
                words=None  # V1ではwordsがない場合がある
            )
        ],
        language="ja",
        original_audio_path="test.wav",
        model_size="large",
        processing_time=10.0
    )
    
    try:
        v2_result = v1_result.to_v2_format()
        print("✓ V1からV2への変換成功")
        
        # wordsフィールドの検証
        try:
            v2_result.require_valid_words()
            print("✗ wordsがないのに検証をパスしてしまった")
        except WordsFieldMissingError:
            print("✓ 正しくwordsフィールドの欠落を検出")
            
    except Exception as e:
        print(f"✗ 変換エラー: {type(e).__name__}: {e}")


def test_partial_words_recovery():
    """部分的なwords情報の復旧テスト"""
    print("\n=== 部分的なwords情報の復旧テスト ===")
    
    # 一部のwordにタイムスタンプが欠落している場合
    segment = TranscriptionSegmentV2(
        id=1,
        start=0.0,
        end=3.0,
        text="あいうえお",
        words=[
            WordInfo(start=0.0, end=0.5, word="あ"),
            WordInfo(start=None, end=None, word="い"),  # タイムスタンプ欠落
            WordInfo(start=1.0, end=1.5, word="う"),
            WordInfo(start=None, end=None, word="え"),  # タイムスタンプ欠落
            WordInfo(start=2.0, end=3.0, word="お")
        ]
    )
    
    # estimate_missing_timestamps()のテスト
    if hasattr(segment, 'estimate_missing_timestamps'):
        try:
            recovered = segment.estimate_missing_timestamps()
            print("✓ タイムスタンプの推定処理を実行")
            
            # 推定されたタイムスタンプを確認
            for i, word in enumerate(recovered.words):
                if word.start is None or word.end is None:
                    print(f"  ✗ Word '{word.word}' のタイムスタンプが推定されなかった")
                else:
                    print(f"  ✓ Word '{word.word}': {word.start:.2f} - {word.end:.2f}")
                    
        except Exception as e:
            print(f"✗ タイムスタンプ推定エラー: {e}")
    else:
        print("- estimate_missing_timestamps()メソッドは未実装")


def test_search_functionality():
    """検索機能のテスト"""
    print("\n=== 検索機能のテスト ===")
    
    # 正常なセグメントで検索
    segment = TranscriptionSegmentV2(
        id=1,
        start=0.0,
        end=5.0,
        text="これはテストです",
        words=[
            WordInfo(start=0.0, end=1.0, word="これ"),
            WordInfo(start=1.0, end=2.0, word="は"),
            WordInfo(start=2.0, end=3.5, word="テスト"),
            WordInfo(start=3.5, end=4.5, word="で"),
            WordInfo(start=4.5, end=5.0, word="す")
        ]
    )
    
    # 文字位置での単語検索
    test_positions = [0, 2, 3, 5, 7, 10]  # 各文字の位置
    
    for pos in test_positions:
        word = segment.get_word_at_position(pos)
        if word:
            print(f"✓ 位置 {pos}: '{word.word}' ({word.start:.1f}s - {word.end:.1f}s)")
        else:
            if pos >= len(segment.text):
                print(f"✓ 位置 {pos}: 範囲外（正常）")
            else:
                print(f"✗ 位置 {pos}: 単語が見つからない（エラー）")


def test_alignment_validation():
    """アライメント結果の検証テスト"""
    print("\n=== アライメント結果の検証テスト ===")
    
    from core.models import AlignmentResult
    
    # 成功率が低いアライメント結果
    low_success_result = AlignmentResult(
        segments=[
            TranscriptionSegmentV2(
                id=1,
                start=0.0,
                end=2.0,
                text="テスト",
                words=[WordInfo(start=0.0, end=2.0, word="テスト")]
            )
        ],
        language="ja",
        alignment_stats={
            "total_segments": 10,
            "successful_segments": 3,  # 30%の成功率
            "failed_segments": 7
        }
    )
    
    # 検証
    is_valid, message = low_success_result.validate()
    if not is_valid:
        print(f"✓ 低い成功率を正しく検出: {message}")
    else:
        print("✗ 低い成功率を検出できなかった")
    
    # 高い成功率のアライメント結果
    high_success_result = AlignmentResult(
        segments=[
            TranscriptionSegmentV2(
                id=1,
                start=0.0,
                end=2.0,
                text="テスト",
                words=[WordInfo(start=0.0, end=2.0, word="テスト")]
            )
        ],
        language="ja",
        alignment_stats={
            "total_segments": 10,
            "successful_segments": 9,  # 90%の成功率
            "failed_segments": 1
        }
    )
    
    is_valid, message = high_success_result.validate()
    if is_valid:
        print("✓ 高い成功率を正しく判定")
    else:
        print(f"✗ 高い成功率なのにエラー: {message}")


def run_all_edge_case_tests():
    """全エッジケーステストを実行"""
    print("="*50)
    print("エッジケーステスト")
    print("="*50)
    
    tests = [
        test_words_validation,
        test_v1_to_v2_conversion,
        test_partial_words_recovery,
        test_search_functionality,
        test_alignment_validation
    ]
    
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"\n✗ テスト '{test.__name__}' で予期しないエラー: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*50)
    print("エッジケーステスト完了")
    print("="*50)


if __name__ == "__main__":
    run_all_edge_case_tests()