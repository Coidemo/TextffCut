#!/usr/bin/env python3
"""
v0.9.7でのAPIモードアライメント問題を調査するテストスクリプト
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

# ログ設定
logging.basicConfig(level=logging.DEBUG)
logger = get_logger(__name__)

def test_api_alignment():
    """APIモードでのアライメント処理をテスト"""
    print("=== v0.9.7 APIモードアライメントテスト ===")
    
    # テスト用の短い音声ファイルを作成
    test_audio_path = create_test_audio()
    
    # 設定
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.getenv('TEXTFFCUT_API_KEY', 'test-key')
    config.transcription.api_provider = "openai"
    config.transcription.language = "ja"
    
    # アライメントを分離モードで実行
    config.transcription.api_align_in_subprocess = True
    
    # APITranscriberを初期化
    transcriber = APITranscriber(config)
    
    # テスト用のセグメントを作成（APIレスポンスを模擬）
    test_segments = [
        {
            'start': 0.0,
            'end': 2.0,
            'text': 'これはテストです'
        },
        {
            'start': 2.0,
            'end': 4.0,
            'text': '日本語のアライメント'
        }
    ]
    
    try:
        # アライメント処理を実行
        print("\n1. アライメントサブプロセスを実行...")
        aligned_segments = transcriber._align_in_subprocess(
            test_audio_path,
            test_segments,
            None  # progress_callback
        )
        
        print(f"\n2. アライメント結果: {len(aligned_segments)}セグメント")
        
        # 各セグメントの詳細を表示
        for i, seg in enumerate(aligned_segments):
            print(f"\nセグメント {i+1}:")
            print(f"  テキスト: {seg.get('text', '')}")
            print(f"  時間: {seg.get('start', 0):.2f} - {seg.get('end', 0):.2f}")
            
            words = seg.get('words', [])
            print(f"  words数: {len(words)}")
            
            if words:
                print("  最初のword:")
                word = words[0]
                print(f"    word: {word.get('word', '')}")
                print(f"    start: {word.get('start', 'None')}")
                print(f"    end: {word.get('end', 'None')}")
            else:
                print("  ⚠️ wordsフィールドが空です!")
                
    except Exception as e:
        print(f"\n❌ エラー発生: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # クリーンアップ
        if os.path.exists(test_audio_path):
            os.unlink(test_audio_path)
    
def create_test_audio():
    """テスト用の短い音声ファイルを作成"""
    import subprocess
    
    # 一時ファイル
    temp_wav = tempfile.mktemp(suffix='.wav')
    
    # 4秒の無音WAVファイルを生成
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'anullsrc=r=16000:cl=mono:d=4',
        '-ar', '16000',
        '-ac', '1',
        temp_wav
    ]
    
    subprocess.run(cmd, capture_output=True)
    print(f"テスト音声を作成: {temp_wav}")
    
    return temp_wav

if __name__ == "__main__":
    test_api_alignment()