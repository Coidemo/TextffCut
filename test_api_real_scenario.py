#!/usr/bin/env python3
"""
実際のエラーシナリオを再現
"""
import os
import sys
import json
import tempfile
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.transcription_api import APITranscriber
from utils.logging import get_logger

# ログ設定を詳細に
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = get_logger(__name__)

def test_real_scenario():
    """実際のエラーシナリオを再現"""
    print("=== 実際のAPIモードエラーシナリオ再現 ===")
    
    # 設定
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.getenv('TEXTFFCUT_API_KEY', '')
    config.transcription.api_provider = "openai"
    config.transcription.language = "ja"
    config.transcription.api_align_in_subprocess = True
    
    # APITranscriberを初期化
    transcriber = APITranscriber(config)
    
    # テスト用のAPIレスポンスセグメントを作成（実際のAPIレスポンスを模擬）
    api_segments = []
    for i in range(5):  # 5つのセグメント
        api_segments.append({
            'start': i * 2.0,
            'end': (i + 1) * 2.0,
            'text': f'これはセグメント{i+1}のテキストです。'
        })
    
    print(f"\nAPIセグメント数: {len(api_segments)}")
    
    # テスト音声ファイルを作成
    test_audio = create_test_audio(10)  # 10秒の音声
    
    try:
        # _align_in_subprocessを直接呼び出し
        print("\n_align_in_subprocess を実行中...")
        
        # 進捗コールバック
        def progress_callback(progress, message):
            print(f"  進捗: {progress:.1%} - {message}")
        
        aligned_segments = transcriber._align_in_subprocess(
            test_audio,
            api_segments,
            progress_callback
        )
        
        print(f"\nアライメント完了: {len(aligned_segments)}セグメント")
        
        # 結果を詳細に確認
        for i, seg in enumerate(aligned_segments):
            print(f"\nセグメント {i+1}:")
            print(f"  テキスト: {seg.get('text', '')}")
            words = seg.get('words', [])
            print(f"  words数: {len(words)}")
            
            if not words:
                print("  ⚠️ wordsフィールドが空です！")
            else:
                print(f"  最初のword: {words[0]}")
                
    except Exception as e:
        print(f"\n❌ エラー発生: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # エラーの詳細を調査
        print("\n=== エラー詳細調査 ===")
        print(f"audio_path: {test_audio}")
        print(f"ファイル存在: {os.path.exists(test_audio)}")
        
    finally:
        # クリーンアップ
        if os.path.exists(test_audio):
            os.unlink(test_audio)

def create_test_audio(duration):
    """テスト用の音声ファイルを作成"""
    import subprocess
    
    temp_wav = tempfile.mktemp(suffix='.wav')
    
    # 指定秒数の無音WAVファイルを生成
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', f'anullsrc=r=16000:cl=mono:d={duration}',
        '-ar', '16000',
        '-ac', '1',
        temp_wav
    ]
    
    subprocess.run(cmd, capture_output=True)
    print(f"テスト音声を作成: {temp_wav} ({duration}秒)")
    
    return temp_wav

if __name__ == "__main__":
    # APIキーが設定されているか確認
    if not os.getenv('TEXTFFCUT_API_KEY'):
        print("警告: TEXTFFCUT_API_KEY環境変数が設定されていません")
        print("実際のAPIコールはスキップされます")
    
    test_real_scenario()