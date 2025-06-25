"""
波形表示統合テスト（librosaなしでも動作することを確認）
"""

import os
import sys

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """必要なモジュールがインポートできることを確認"""
    print("Testing imports...")

    try:
        from core.waveform_processor import WaveformData, WaveformProcessor

        print("✓ waveform_processor imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import waveform_processor: {e}")
        return False

    try:
        from ui.waveform_display import WaveformDisplay

        print("✓ waveform_display imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import waveform_display: {e}")
        return False

    try:
        from ui.timeline_editor import render_timeline_editor

        print("✓ timeline_editor imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import timeline_editor: {e}")
        return False

    return True


def test_waveform_processor():
    """WaveformProcessorの基本機能をテスト"""
    print("\nTesting WaveformProcessor...")

    from core.waveform_processor import WaveformData, WaveformProcessor

    processor = WaveformProcessor()

    # キャッシュキー生成
    key = processor.get_cache_key("test.mp4", "seg001")
    print(f"✓ Cache key generated: {key[:20]}...")

    # librosaなしでも波形データが返されることを確認
    waveform_data = processor.extract_waveform("dummy_video.mp4", 0.0, 5.0, "test_segment")

    assert isinstance(waveform_data, WaveformData)
    assert waveform_data.segment_id == "test_segment"
    assert waveform_data.duration == 5.0
    print("✓ WaveformData created successfully (empty due to no librosa)")

    return True


def test_waveform_display():
    """WaveformDisplayの基本機能をテスト"""
    print("\nTesting WaveformDisplay...")

    from core.waveform_processor import WaveformData
    from ui.waveform_display import WaveformDisplay

    display = WaveformDisplay()

    # 空の波形データでも表示できることを確認
    waveform_data = WaveformData(
        segment_id="test", sample_rate=44100, samples=[], duration=5.0, start_time=0.0, end_time=5.0
    )

    fig = display.render_waveform(waveform_data)
    # plotlyがない場合はNoneが返される
    print("✓ Waveform render called successfully (returns None without plotly)")

    # タイムライン概要表示
    segments = [WaveformData("seg1", 44100, [], 2.0, 0.0, 2.0), WaveformData("seg2", 44100, [], 3.0, 5.0, 8.0)]

    overview_fig = display.render_timeline_overview(segments, 10.0)
    # plotlyがない場合はNoneが返される
    print("✓ Timeline overview render called successfully (returns None without plotly)")

    return True


def main():
    """すべてのテストを実行"""
    print("=== Waveform Display Integration Test ===\n")

    tests = [test_imports, test_waveform_processor, test_waveform_display]

    all_passed = True
    for test in tests:
        try:
            if not test():
                all_passed = False
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with error: {e}")
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
