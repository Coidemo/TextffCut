"""
修正版のテストスクリプト
"""
import os
import sys
import time
from pathlib import Path

# APIキーを設定
if len(sys.argv) > 1:
    os.environ["OPENAI_API_KEY"] = sys.argv[1]

# 強制低スペックモード
os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"

from config import Config
from core.transcription import Transcriber
from utils.logging import get_logger

logger = get_logger(__name__)


def test_short_video():
    """短い動画でのテスト（6分）"""
    video_path = "/Users/naoki/myProject/TextffCut/videos/001_AI活用の始めの一歩：お笑いAIから学ぶ発想術.mp4"
    
    if not Path(video_path).exists():
        print(f"テスト動画が見つかりません: {video_path}")
        return False
    
    print("\n" + "="*80)
    print("短い動画テスト（6分） - 修正版")
    print("="*80)
    
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.environ.get("OPENAI_API_KEY")
    
    if not config.transcription.api_key:
        print("エラー: APIキーが設定されていません")
        return False
    
    def progress_callback(progress: float, status: str):
        print(f"[{time.strftime('%H:%M:%S')}] {progress:.1%} - {status}")
    
    try:
        transcriber = Transcriber(config)
        
        # キャッシュをクリア
        cache_path = transcriber.get_cache_path(video_path, "whisper-1_api")
        if cache_path.exists():
            os.remove(cache_path)
        
        start_time = time.time()
        result = transcriber.transcribe(
            video_path,
            model_size="whisper-1",
            progress_callback=progress_callback,
            use_cache=False,
            save_cache=True
        )
        end_time = time.time()
        
        print(f"\n処理完了:")
        print(f"  処理時間: {end_time - start_time:.1f}秒")
        print(f"  セグメント数: {len(result.segments)}")
        
        # アライメント成功率を確認
        aligned_segments = sum(1 for seg in result.segments if seg.words is not None)
        print(f"  アライメント成功: {aligned_segments}/{len(result.segments)} ({aligned_segments/len(result.segments)*100:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"エラー発生: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 環境変数をクリーンアップ
        if "TEXTFFCUT_FORCE_LOW_SPEC" in os.environ:
            del os.environ["TEXTFFCUT_FORCE_LOW_SPEC"]


def test_long_video():
    """長い動画でのテスト（65分）"""
    video_path = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）世界は保守かリベラルか？ではなくて変革か維持か？で2つに分かれてる.mp4"
    
    if not Path(video_path).exists():
        print(f"テスト動画が見つかりません: {video_path}")
        return False
    
    print("\n" + "="*80)
    print("長い動画テスト（65分） - 修正版・超最適化モード")
    print("="*80)
    
    # 強制低スペックモード
    os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"
    
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.environ.get("OPENAI_API_KEY")
    
    if not config.transcription.api_key:
        print("エラー: APIキーが設定されていません")
        return False
    
    def progress_callback(progress: float, status: str):
        print(f"[{time.strftime('%H:%M:%S')}] {progress:.1%} - {status}")
    
    try:
        transcriber = Transcriber(config)
        
        # キャッシュをクリア
        cache_path = transcriber.get_cache_path(video_path, "whisper-1_api")
        if cache_path.exists():
            os.remove(cache_path)
        
        start_time = time.time()
        result = transcriber.transcribe(
            video_path,
            model_size="whisper-1",
            progress_callback=progress_callback,
            use_cache=False,
            save_cache=True
        )
        end_time = time.time()
        
        print(f"\n処理完了:")
        print(f"  処理時間: {end_time - start_time:.1f}秒 ({(end_time - start_time)/60:.1f}分)")
        print(f"  セグメント数: {len(result.segments)}")
        
        # アライメント成功率を確認
        aligned_segments = sum(1 for seg in result.segments if seg.words is not None)
        print(f"  アライメント成功: {aligned_segments}/{len(result.segments)} ({aligned_segments/len(result.segments)*100:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"エラー発生: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 環境変数をクリーンアップ
        if "TEXTFFCUT_FORCE_LOW_SPEC" in os.environ:
            del os.environ["TEXTFFCUT_FORCE_LOW_SPEC"]


def main():
    """メインテスト実行"""
    if not os.environ.get("OPENAI_API_KEY") and len(sys.argv) < 2:
        print("エラー: APIキーが必要です")
        print("使用方法: python test_fixed_version.py YOUR_API_KEY")
        return
    
    # 短い動画でテスト
    success1 = test_short_video()
    
    if success1:
        print("\n短い動画のテストが成功しました。")
        print("長い動画のテストを開始しますか？ (y/n): ", end="")
        if input().lower() == 'y':
            # 長い動画でテスト
            success2 = test_long_video()
            
            if success2:
                print("\n✅ すべてのテストが成功しました！")
            else:
                print("\n❌ 長い動画のテストが失敗しました。")
    else:
        print("\n❌ 短い動画のテストが失敗しました。")


if __name__ == "__main__":
    main()