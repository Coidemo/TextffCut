"""
波形表示機能の視覚的確認テスト
実際の動画ファイルを使用して波形を生成し、HTMLファイルとして保存
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.waveform_processor import WaveformProcessor, WaveformData
from ui.waveform_display import WaveformDisplay


def test_waveform_generation():
    """波形生成と表示のテスト"""
    print("=== Waveform Visual Test ===\n")
    
    # videosディレクトリのファイルを探す
    videos_dir = Path("videos")
    if not videos_dir.exists():
        print("❌ 'videos' directory not found")
        return False
    
    video_files = list(videos_dir.glob("*.mp4")) + list(videos_dir.glob("*.mov"))
    if not video_files:
        print("❌ No video files found in 'videos' directory")
        return False
    
    # 最初の動画ファイルを使用
    video_path = str(video_files[0])
    print(f"Using video file: {video_path}")
    
    # 波形処理とテスト用セグメント
    processor = WaveformProcessor()
    display = WaveformDisplay()
    
    # テスト用セグメント（最初の10秒）
    segments = [
        {"id": "seg001", "start": 0.0, "end": 5.0},
        {"id": "seg002", "start": 5.0, "end": 10.0},
        {"id": "seg003", "start": 10.0, "end": 15.0}
    ]
    
    waveform_data_list = []
    
    # 各セグメントの波形データを抽出
    print("\nExtracting waveforms...")
    for seg in segments:
        print(f"  Processing {seg['id']}: {seg['start']:.1f}s - {seg['end']:.1f}s")
        waveform_data = processor.extract_waveform(
            video_path,
            seg['start'],
            seg['end'],
            seg['id']
        )
        waveform_data_list.append(waveform_data)
    
    # 個別セグメントの波形表示
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    
    print("\nGenerating waveform visualizations...")
    
    for i, waveform_data in enumerate(waveform_data_list):
        # 無音領域を検出
        silence_regions = processor.detect_silence_regions(waveform_data)
        
        # 波形を描画
        fig = display.render_waveform(
            waveform_data,
            silence_regions=silence_regions,
            show_time_axis=True
        )
        
        if fig:
            # HTMLファイルとして保存
            output_file = output_dir / f"waveform_{waveform_data.segment_id}.html"
            fig.write_html(str(output_file))
            print(f"  ✓ Saved waveform for {waveform_data.segment_id} to {output_file}")
        else:
            print(f"  ✗ Failed to render waveform for {waveform_data.segment_id}")
    
    # タイムライン概要の表示
    print("\nGenerating timeline overview...")
    overview_fig = display.render_timeline_overview(waveform_data_list, 20.0)
    
    if overview_fig:
        overview_file = output_dir / "timeline_overview.html"
        overview_fig.write_html(str(overview_file))
        print(f"  ✓ Saved timeline overview to {overview_file}")
    else:
        print("  ✗ Failed to render timeline overview")
    
    print(f"\n✅ Test completed! Check the '{output_dir}' directory for results.")
    return True


def test_silence_detection():
    """無音検出の詳細テスト"""
    print("\n=== Silence Detection Test ===\n")
    
    # テスト用の波形データ（正弦波 + 無音部分）
    import numpy as np
    
    # サンプルレート44.1kHz、5秒間
    sr = 44100
    duration = 5.0
    t = np.linspace(0, duration, int(sr * duration))
    
    # 波形生成：最初の1秒は音あり、次の1秒は無音、その後音あり
    samples = []
    for i, time in enumerate(t):
        if 1.0 <= time <= 2.0 or 3.5 <= time <= 4.0:
            # 無音部分
            samples.append(0.0001 * np.random.randn())
        else:
            # 音声部分（440Hz）
            samples.append(0.8 * np.sin(2 * np.pi * 440 * time))
    
    # WaveformDataを作成
    waveform_data = WaveformData(
        segment_id="silence_test",
        sample_rate=sr,
        samples=samples,
        duration=duration,
        start_time=0.0,
        end_time=duration
    )
    
    # 無音検出
    processor = WaveformProcessor()
    silence_regions = processor.detect_silence_regions(waveform_data)
    
    print(f"Total samples: {len(samples)}")
    print(f"Detected {len(silence_regions)} silence regions:")
    
    for start_idx, end_idx in silence_regions:
        start_time = start_idx / sr * duration / len(samples)
        end_time = end_idx / sr * duration / len(samples)
        print(f"  - {start_time:.2f}s to {end_time:.2f}s")
    
    # 可視化
    display = WaveformDisplay()
    fig = display.render_waveform(
        waveform_data,
        silence_regions=silence_regions,
        show_time_axis=True
    )
    
    if fig:
        output_file = Path("test_output") / "silence_detection_test.html"
        fig.write_html(str(output_file))
        print(f"\n✓ Saved visualization to {output_file}")
    
    return True


if __name__ == "__main__":
    # 波形生成テスト
    success1 = test_waveform_generation()
    
    # 無音検出テスト
    success2 = test_silence_detection()
    
    if success1 and success2:
        print("\n🎉 All visual tests completed successfully!")
    else:
        print("\n❌ Some tests failed!")