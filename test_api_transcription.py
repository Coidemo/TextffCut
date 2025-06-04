"""
API文字起こしのテストスクリプト
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from core.transcription import Transcriber
from pathlib import Path


def test_api_transcription():
    """API文字起こしのテスト"""
    print("="*80)
    print("API文字起こしテスト")
    print("="*80)
    
    # APIキーを設定
    api_key = "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"
    
    # テスト動画を探す
    test_videos = ["test.mp4", "videos/test.mp4", "001_AI活用の始めの一歩：お笑いAIから学ぶ発想術.mp4"]
    video_path = None
    
    for video in test_videos:
        if os.path.exists(video):
            video_path = video
            break
    
    if not video_path:
        print("❌ テスト動画が見つかりません")
        return False
    
    print(f"✅ テスト動画: {video_path}")
    
    # 設定をAPI使用に変更
    config.transcription.use_api = True
    config.transcription.api_key = api_key
    config.transcription.api_provider = "openai"
    
    # Transcriberを初期化
    transcriber = Transcriber(config)
    
    # プログレスコールバック
    def progress_callback(progress: float, status: str):
        print(f"  進捗: {progress*100:.1f}% - {status}")
    
    try:
        # 各モードでテスト（autoモードのみ先に実行）
        modes = ["auto"]
        
        for mode in modes:
            print(f"\n[{mode}モードのテスト]")
            
            # キャッシュは使わずに新規実行
            result = transcriber.transcribe(
                video_path,
                model_size="whisper-1",
                progress_callback=progress_callback,
                use_cache=False,
                save_cache=False,
                optimization_mode=mode
            )
            
            if result:
                print(f"✅ {mode}モード成功")
                print(f"   セグメント数: {len(result.segments)}")
                print(f"   処理時間: {result.processing_time:.1f}秒")
                if len(result.segments) > 0:
                    print(f"   最初のセグメント: {result.segments[0].text[:50]}...")
            else:
                print(f"❌ {mode}モード失敗")
                return False
                
    except Exception as e:
        print(f"\n❌ エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*80)
    print("🎉 すべてのテストが成功しました！")
    print("="*80)
    return True


if __name__ == "__main__":
    success = test_api_transcription()
    sys.exit(0 if success else 1)