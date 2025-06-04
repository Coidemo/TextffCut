"""
シンプルなAPI文字起こしテスト
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 環境変数でAPI設定
os.environ['TEXTFFCUT_USE_API'] = 'true'
os.environ['TEXTFFCUT_API_KEY'] = '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'

from config import config
from core.transcription import Transcriber


def main():
    """シンプルなテスト"""
    print("="*60)
    print("API文字起こしシンプルテスト")
    print("="*60)
    
    # テスト動画を探す
    test_videos = ["test.mp4", "videos/test.mp4", "001_AI活用の始めの一歩：お笑いAIから学ぶ発想術.mp4"]
    video_path = None
    
    for video in test_videos:
        if os.path.exists(video):
            video_path = video
            break
    
    if not video_path:
        # 最初に見つかった動画を使用
        import glob
        mp4_files = glob.glob("*.mp4") + glob.glob("videos/*.mp4")
        if mp4_files:
            video_path = mp4_files[0]
        else:
            print("❌ 動画ファイルが見つかりません")
            return False
    
    # 設定を確認
    config.transcription.use_api = True
    config.transcription.api_key = os.environ['TEXTFFCUT_API_KEY']
    
    print(f"✅ APIモード: {config.transcription.use_api}")
    print(f"✅ APIキー: {config.transcription.api_key[:20]}...")
    print(f"✅ テスト動画: {video_path}")
    
    # Transcriberを初期化
    transcriber = Transcriber(config)
    
    try:
        print("\n文字起こし開始...")
        result = transcriber.transcribe(
            video_path,
            model_size="whisper-1",
            use_cache=False,
            save_cache=False,
            optimization_mode="auto"
        )
        
        if result:
            print("\n✅ 文字起こし成功！")
            print(f"セグメント数: {len(result.segments)}")
            print(f"処理時間: {result.processing_time:.1f}秒")
            
            # 最初の3セグメントを表示
            print("\n最初の3セグメント:")
            for i, seg in enumerate(result.segments[:3]):
                print(f"{i+1}. [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
            
            return True
        else:
            print("❌ 文字起こし失敗")
            return False
            
    except Exception as e:
        print(f"\n❌ エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    print("\n" + "="*60)
    if success:
        print("✅ テスト成功")
    else:
        print("❌ テスト失敗")
    sys.exit(0 if success else 1)