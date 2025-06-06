#!/usr/bin/env python
"""
インポートテストスクリプト
新しいモジュールが正しくインポートできるかテスト
"""

import sys
import traceback
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """インポートテスト"""
    results = {"success": [], "failed": []}
    
    # テストするインポート
    test_cases = [
        # 新規ファイルのインポート
        ("core.models", [
            "TranscriptionSegmentV2",
            "TranscriptionResultV2", 
            "ProcessingMetadata",
            "WordInfo",
            "CharInfo",
            "ProcessingStatus",
            "ProcessingStage"
        ]),
        ("core.exceptions", [
            "ProcessingError",
            "WordsFieldMissingError",
            "TranscriptionValidationError",
            "AlignmentValidationError",
            "SubprocessError",
            "RetryExhaustedError"
        ]),
        ("core.interfaces", [
            "ITranscriptionProcessor",
            "IAlignmentProcessor",
            "IUnifiedTranscriber",
            "ICacheManager",
            "IProgressReporter"
        ]),
        ("core.unified_transcriber", [
            "UnifiedTranscriber",
            "DefaultProgressReporter"
        ]),
        ("core.alignment_processor", [
            "AlignmentProcessor"
        ]),
        ("core.retry_handler", [
            "RetryStrategy",
            "AdaptiveRetryStrategy",
            "RetryHandler",
            "with_retry"
        ]),
        ("core.transcription_worker", [
            "LocalTranscriptionWorker"
        ]),
        
        # 既存モジュールの新機能
        ("core.transcription", [
            "TranscriptionResult",
            "TranscriptionSegment",
            "Transcriber"
        ])
    ]
    
    print("=== インポートテスト開始 ===\n")
    
    for module_name, classes in test_cases:
        print(f"--- {module_name} ---")
        
        try:
            # モジュールをインポート
            module = __import__(module_name, fromlist=classes)
            
            # 各クラス/関数をチェック
            missing = []
            for class_name in classes:
                if hasattr(module, class_name):
                    print(f"  ✓ {class_name}")
                else:
                    missing.append(class_name)
                    print(f"  ✗ {class_name} - 見つかりません")
            
            if missing:
                results["failed"].append({
                    "module": module_name,
                    "missing": missing,
                    "error": "一部のクラス/関数が見つかりません"
                })
            else:
                results["success"].append(module_name)
                print(f"  → {module_name}: OK")
                
        except ImportError as e:
            results["failed"].append({
                "module": module_name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            print(f"  ✗ インポートエラー: {e}")
        except Exception as e:
            results["failed"].append({
                "module": module_name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            print(f"  ✗ エラー: {e}")
        
        print()
    
    # 結果サマリー
    print("=== 結果サマリー ===")
    print(f"成功: {len(results['success'])}件")
    print(f"失敗: {len(results['failed'])}件")
    
    if results["failed"]:
        print("\n=== 失敗の詳細 ===")
        for failure in results["failed"]:
            print(f"\nモジュール: {failure['module']}")
            print(f"エラー: {failure['error']}")
            if 'missing' in failure:
                print(f"不足: {failure['missing']}")
            if 'traceback' in failure and len(results["failed"]) < 3:
                print("トレースバック:")
                print(failure['traceback'])
    
    return results


def test_cross_module_imports():
    """モジュール間の相互インポートテスト"""
    print("\n=== モジュール間インポートテスト ===\n")
    
    test_cases = [
        # unified_transcriberが他のモジュールを使えるか
        {
            "name": "UnifiedTranscriberの依存関係",
            "code": """
from core.unified_transcriber import UnifiedTranscriber
from core.models import ProcessingRequest, TranscriptionResultV2
from config import Config

# インスタンス化テスト
config = Config()
transcriber = UnifiedTranscriber(config)
print("✓ UnifiedTranscriberのインスタンス化成功")
"""
        },
        
        # main.pyから新機能を使えるか
        {
            "name": "main.pyからの新機能アクセス",
            "code": """
from core.exceptions import WordsFieldMissingError
from core.transcription import TranscriptionResult

# 旧形式のTranscriptionResultでV2変換をテスト
result = TranscriptionResult(
    language="ja",
    segments=[],
    original_audio_path="test.mp4",
    model_size="base",
    processing_time=0.0
)

# V2形式への変換
v2_result = result.to_v2_format()
print("✓ V2形式への変換成功")
"""
        }
    ]
    
    for test in test_cases:
        print(f"--- {test['name']} ---")
        try:
            exec(test['code'])
        except Exception as e:
            print(f"✗ エラー: {e}")
            traceback.print_exc()
        print()


def test_type_compatibility():
    """型の互換性テスト"""
    print("\n=== 型互換性テスト ===\n")
    
    try:
        from core.models import TranscriptionSegmentV2, WordInfo
        from core.transcription import TranscriptionSegment
        
        # 新旧セグメントの変換テスト
        old_segment = TranscriptionSegment(
            start=0.0,
            end=1.0,
            text="テスト",
            words=[{"word": "テスト", "start": 0.0, "end": 1.0}]
        )
        
        # 新形式に変換
        words = [WordInfo(
            word=w["word"],
            start=w.get("start"),
            end=w.get("end")
        ) for w in old_segment.words] if old_segment.words else None
        
        new_segment = TranscriptionSegmentV2(
            id="test",
            text=old_segment.text,
            start=old_segment.start,
            end=old_segment.end,
            words=words,
            transcription_completed=True,
            alignment_completed=bool(words)
        )
        
        print("✓ 旧形式から新形式への変換成功")
        print(f"  - 旧形式: TranscriptionSegment")
        print(f"  - 新形式: TranscriptionSegmentV2")
        print(f"  - words数: {len(new_segment.words) if new_segment.words else 0}")
        
    except Exception as e:
        print(f"✗ 型互換性エラー: {e}")
        traceback.print_exc()


def main():
    """メイン処理"""
    # インポートテスト
    import_results = test_imports()
    
    # 成功した場合のみ追加テスト
    if len(import_results["failed"]) == 0:
        test_cross_module_imports()
        test_type_compatibility()
    else:
        print("\n⚠️ 基本インポートに失敗したため、追加テストはスキップします")


if __name__ == "__main__":
    main()