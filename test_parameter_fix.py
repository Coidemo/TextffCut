#!/usr/bin/env python3
"""
パラメータ修正の動作確認テスト

実際のメソッド呼び出しでパラメータが正しくマッピングされているか確認
"""
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_video_processor_params():
    """VideoProcessorのパラメータを確認"""
    print("=== VideoProcessor パラメータ確認 ===")

    import inspect

    from core.video import VideoProcessor

    # remove_silence_newのパラメータ
    sig = inspect.signature(VideoProcessor.remove_silence_new)
    params = list(sig.parameters.keys())
    print(f"\nremove_silence_new パラメータ: {params}")

    # extract_segmentのパラメータ
    sig = inspect.signature(VideoProcessor.extract_segment)
    params = list(sig.parameters.keys())
    print(f"extract_segment パラメータ: {params}")

    # combine_videosメソッドが存在するか
    if hasattr(VideoProcessor, "combine_videos"):
        print("✓ combine_videos メソッドが存在")
    else:
        print("✗ combine_videos メソッドが存在しない")
        if hasattr(VideoProcessor, "concatenate_videos"):
            print("  → concatenate_videos メソッドが存在")


def test_transcriber_params():
    """Transcriberのパラメータを確認"""
    print("\n=== Transcriber パラメータ確認 ===")

    import inspect

    from core.transcription import Transcriber

    # transcribeのパラメータ
    sig = inspect.signature(Transcriber.transcribe)
    params = list(sig.parameters.keys())
    print(f"\ntranscribe パラメータ: {params}")


def test_exporter_params():
    """Exporterのパラメータを確認"""
    print("\n=== Exporter パラメータ確認 ===")

    import inspect

    from core.export import FCPXMLExporter, XMEMLExporter

    # FCPXMLExporter.exportのパラメータ
    sig = inspect.signature(FCPXMLExporter.export)
    params = list(sig.parameters.keys())
    print(f"\nFCPXMLExporter.export パラメータ: {params}")

    # XMEMLExporter.exportのパラメータ
    sig = inspect.signature(XMEMLExporter.export)
    params = list(sig.parameters.keys())
    print(f"XMEMLExporter.export パラメータ: {params}")


def test_actual_calls():
    """実際の呼び出しが動作するかテスト"""
    print("\n=== 実際の呼び出しテスト ===")

    from unittest.mock import patch

    from config import config
    from services.video_processing_service import VideoProcessingService

    service = VideoProcessingService(config)

    # VideoProcessor.remove_silence_newの呼び出しを確認
    with patch.object(service.video_processor, "remove_silence_new") as mock_method:
        mock_method.return_value = [(0.0, 5.0)]

        # 必要な他のメソッドもモック
        with patch.object(service, "validate_file_exists") as mock_validate:
            mock_validate.return_value = Path("/tmp/test.mp4")

            from core.models import TranscriptionSegmentV2

            segments = [TranscriptionSegmentV2(id=0, start=0.0, end=5.0, text="test", words=[])]

            try:
                result = service.remove_silence(video_path="/tmp/test.mp4", segments=segments, threshold=-35.0)

                # メソッドが呼ばれたか確認
                if mock_method.called:
                    call_args = mock_method.call_args[1]
                    print("\n✓ remove_silence_new が呼ばれました")
                    print(f"  パラメータ: {list(call_args.keys())}")
                else:
                    print("\n✗ remove_silence_new が呼ばれませんでした")

            except Exception as e:
                print(f"\n✗ エラー: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("パラメータ修正確認テスト")
    print("=" * 60)

    test_video_processor_params()
    test_transcriber_params()
    test_exporter_params()
    test_actual_calls()

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
