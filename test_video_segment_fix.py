"""
VideoSegmentクラスの使用方法が正しいことを確認するテスト
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from core.video import VideoSegment


def test_video_segment_creation():
    """VideoSegmentの作成をテスト"""
    print("=== VideoSegment作成テスト ===")
    
    # 正しい使用方法
    try:
        segment = VideoSegment(start=10.5, end=20.5)
        assert segment.start == 10.5
        assert segment.end == 20.5
        assert segment.duration == 10.0
        assert segment.output_path is None
        print("✓ VideoSegmentが正しく作成されました")
    except Exception as e:
        print(f"✗ VideoSegment作成エラー: {e}")
        raise
    
    # output_pathを指定した場合
    try:
        segment_with_path = VideoSegment(start=0.0, end=5.0, output_path="/tmp/test.mp4")
        assert segment_with_path.output_path == "/tmp/test.mp4"
        print("✓ output_path付きVideoSegmentが正しく作成されました")
    except Exception as e:
        print(f"✗ output_path付きVideoSegment作成エラー: {e}")
        raise
    
    # textパラメータは存在しないことを確認
    try:
        # これはTypeErrorが発生するはず
        segment_with_text = VideoSegment(start=0.0, end=1.0, text="test")
        print("✗ textパラメータが受け入れられてしまいました（エラーのはず）")
        assert False, "VideoSegmentにtextパラメータが存在してはいけない"
    except TypeError as e:
        print(f"✓ 予期したTypeErrorが発生: {e}")
    
    print("\n✅ VideoSegment作成テスト完了")


def test_main_py_usage():
    """main.pyでのVideoSegmentの使用が正しいことを確認"""
    print("\n=== main.pyでのVideoSegment使用確認 ===")
    
    # main.pyのコードを確認
    main_py_path = Path(__file__).parent / "main.py"
    
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # VideoSegmentにtext=が含まれていないことを確認
    if "VideoSegment(start=start, end=end, text=" in content:
        print("✗ main.pyにまだtext=パラメータを使用している箇所があります")
        assert False
    else:
        print("✓ main.pyでVideoSegmentのtext=パラメータは使用されていません")
    
    # 正しい使用方法になっていることを確認
    if "VideoSegment(start=start, end=end)" in content:
        print("✓ main.pyでVideoSegmentが正しく使用されています")
    else:
        print("⚠️ main.pyでVideoSegmentの使用方法を確認してください")
    
    print("\n✅ main.pyでのVideoSegment使用確認完了")


if __name__ == "__main__":
    try:
        test_video_segment_creation()
        test_main_py_usage()
        
        print("\n" + "="*50)
        print("🎉 すべてのVideoSegmentテストが成功しました！")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)