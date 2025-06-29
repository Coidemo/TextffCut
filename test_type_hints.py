#!/usr/bin/env python3
"""
型ヒントのテストと検証

型定義が正しく機能することを確認する。
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from core.models_typed import ProcessingMetadata, TranscriptionResultV2, TranscriptionSegmentV2, WordInfoData
from core.types import (
    ModelSize,
    Page,
    ProgressCallback,
    Result,
    TimeSeconds,
    TranscriptionOptions,
    VideoMetadata,
    VideoPath,
    is_video_format,
    to_path,
)


def test_basic_types() -> None:
    """基本型のテスト"""
    print("=== 基本型のテスト ===")

    # パス型
    video_path1: VideoPath = "/path/to/video.mp4"
    video_path2: VideoPath = Path("/path/to/video.mp4")
    print(f"VideoPath (str): {video_path1}")
    print(f"VideoPath (Path): {video_path2}")

    # 時間型
    duration: TimeSeconds = 123.45
    print(f"Duration: {duration}秒")

    # モデルサイズ
    model: ModelSize = "medium"
    # model = "invalid"  # これは型エラーになるはず
    print(f"Model size: {model}")

    print()


def test_typed_dict() -> None:
    """TypedDictのテスト"""
    print("=== TypedDictのテスト ===")

    # VideoMetadata
    metadata: VideoMetadata = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "duration": 120.0,
        "codec": "h264",
        "bitrate": 5000000,
        "audio_codec": "aac",
        "audio_sample_rate": 48000,
        "audio_channels": 2,
    }
    print(f"Video metadata: {metadata['width']}x{metadata['height']}")

    # TranscriptionOptions（部分的な指定）
    options: TranscriptionOptions = {"language": "ja", "model_size": "large-v3", "batch_size": 16}
    print(f"Transcription options: {options}")

    print()


def test_protocol() -> None:
    """Protocolのテスト"""
    print("=== Protocolのテスト ===")

    # ProgressCallback実装
    def my_progress_callback(progress: float, message: str) -> None:
        print(f"[{progress:.1%}] {message}")

    # Protocolに適合する関数
    callback: ProgressCallback = my_progress_callback
    callback(0.5, "処理中...")

    # クラスベースの実装も可能
    class ProgressReporter:
        def __call__(self, progress: float, message: str) -> None:
            print(f"Progress: {progress:.2f} - {message}")

    reporter: ProgressCallback = ProgressReporter()
    reporter(0.75, "もうすぐ完了")

    print()


def test_generic_types() -> None:
    """ジェネリック型のテスト"""
    print("=== ジェネリック型のテスト ===")

    # Result型
    success_result: Result[dict[str, str]] = Result(
        success=True, data={"message": "成功しました"}, metadata={"timestamp": "2025-06-08"}
    )
    print(f"Success result: {success_result.data}")

    error_result: Result[None] = Result(success=False, error="エラーが発生しました")
    print(f"Error result: {error_result.error}")

    # Page型
    segments = [f"Segment {i}" for i in range(10)]
    page: Page[str] = Page(items=segments[:5], total=len(segments), page=1, page_size=5)
    print(f"Page 1: {page.items}")
    print(f"Has next: {page.has_next}")

    print()


def test_model_types() -> None:
    """モデルクラスの型テスト"""
    print("=== モデルクラスの型テスト ===")

    # WordInfoData
    word: WordInfoData = WordInfoData(word="こんにちは", start=1.0, end=1.5, confidence=0.95)
    print(f"Word: {word.word} ({word.start}-{word.end}s)")

    # TranscriptionSegmentV2
    segment: TranscriptionSegmentV2 = TranscriptionSegmentV2(
        id="seg_1",
        text="これはテストです",
        start=0.0,
        end=3.0,
        words=[word],
        language="ja",
        transcription_completed=True,
    )

    # 型安全なメソッド呼び出し
    is_valid: bool = segment.has_valid_alignment()
    validation_result: tuple[bool, str | None] = segment.validate_for_search()

    print(f"Segment: {segment.text}")
    print(f"Valid alignment: {is_valid}")
    print(f"Validation: {validation_result}")

    print()


def test_type_guards() -> None:
    """型ガード関数のテスト"""
    print("=== 型ガード関数のテスト ===")

    # ビデオフォーマットチェック
    extensions = [".mp4", ".mov", ".txt", ".pdf"]
    for ext in extensions:
        is_video = is_video_format(ext)
        print(f"{ext}: {'動画' if is_video else '非動画'}")

    # パス変換
    str_path = "/path/to/file.mp4"
    path_obj = to_path(str_path)
    print(f"Converted path: {path_obj} (type: {type(path_obj).__name__})")

    print()


def test_complex_scenario() -> None:
    """複雑なシナリオのテスト"""
    print("=== 複雑なシナリオのテスト ===")

    # メタデータ付き文字起こし結果
    metadata: ProcessingMetadata = ProcessingMetadata(
        video_path="/videos/sample.mp4",
        video_duration=300.0,
        processing_mode="local",
        model_size="medium",
        language="ja",
    )

    segments: list[TranscriptionSegmentV2] = [
        TranscriptionSegmentV2(
            id=f"seg_{i}",
            text=f"セグメント{i}のテキスト",
            start=i * 10.0,
            end=(i + 1) * 10.0,
            transcription_completed=True,
        )
        for i in range(3)
    ]

    result: TranscriptionResultV2 = TranscriptionResultV2(
        segments=segments, metadata=metadata, transcription_status="completed"
    )

    # 型安全な操作
    result.update_statistics()
    result.get_valid_segments()
    is_complete: bool = result.is_complete()

    print(f"Total segments: {result.total_segments}")
    print(f"Transcribed: {result.transcribed_segments}")
    print(f"Is complete: {is_complete}")

    # 検証
    is_valid, errors = result.validate_for_processing()
    if not is_valid:
        print(f"Validation errors: {errors}")
    else:
        print("Validation passed!")

    print()


def run_all_tests() -> None:
    """すべてのテストを実行"""
    test_basic_types()
    test_typed_dict()
    test_protocol()
    test_generic_types()
    test_model_types()
    test_type_guards()
    test_complex_scenario()

    print("=== すべてのテストが完了しました ===")


if __name__ == "__main__":
    run_all_tests()
