#!/usr/bin/env python
"""
アライメント専用ワーカープロセス

APIで取得した文字起こし結果に対して、
WhisperXでアライメント処理を行う。
メモリリーク対策のため、処理完了後に自動終了。
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def send_progress(progress: float, message: str = ""):
    """プログレス情報を親プロセスに送信"""
    print(f"PROGRESS:{progress}|{message}", flush=True)


def process_alignment(
    audio_path: str,
    api_segments: List[Dict[str, Any]],
    language: str,
    chunk_seconds: int = 300
) -> List[Dict[str, Any]]:
    """
    アライメント処理を実行
    
    Args:
        audio_path: 音声ファイルパス
        api_segments: API結果のセグメントリスト
        language: 言語コード
        chunk_seconds: チャンクサイズ（秒）
    
    Returns:
        アライメント済みセグメントリスト
    """
    import whisperx
    import numpy as np
    
    logger.info(f"アライメント処理開始: {len(api_segments)}セグメント")
    
    # 音声を読み込み
    audio = whisperx.load_audio(audio_path)
    audio_duration = len(audio) / 16000  # 16kHz
    
    # アライメントモデルを読み込み
    try:
        align_model, align_meta = whisperx.load_align_model(
            language_code=language,
            device="cpu"
        )
        logger.info("アライメントモデル読み込み完了")
    except Exception as e:
        logger.error(f"アライメントモデル読み込みエラー: {e}")
        # アライメントなしで返す
        return api_segments
    
    # 大きなチャンクで処理
    aligned_segments = []
    chunk_size = chunk_seconds * 16000  # サンプル数
    
    for chunk_start in range(0, len(audio), chunk_size):
        chunk_end = min(chunk_start + chunk_size, len(audio))
        chunk_audio = audio[chunk_start:chunk_end]
        
        start_time = chunk_start / 16000
        end_time = chunk_end / 16000
        
        # このチャンクに含まれるセグメントを抽出
        chunk_segments = []
        for seg in api_segments:
            seg_start = seg.get('start', 0)
            seg_end = seg.get('end', 0)
            
            # セグメントがチャンクと重なる場合
            if seg_start < end_time and seg_end > start_time:
                # チャンク内での相対時間に変換
                relative_seg = {
                    'start': max(0, seg_start - start_time),
                    'end': min(chunk_seconds, seg_end - start_time),
                    'text': seg['text']
                }
                chunk_segments.append(relative_seg)
        
        if not chunk_segments:
            continue
        
        logger.info(f"チャンク {start_time:.1f}s-{end_time:.1f}s: {len(chunk_segments)}セグメント")
        
        try:
            # アライメント実行
            aligned_result = whisperx.align(
                chunk_segments,
                align_model,
                align_meta,
                chunk_audio,
                "cpu",
                return_char_alignments=False
            )
            
            # 結果を絶対時間に戻す
            for seg in aligned_result.get("segments", []):
                aligned_seg = {
                    'start': seg['start'] + start_time,
                    'end': seg['end'] + start_time,
                    'text': seg['text']
                }
                
                # 単語情報があれば追加
                if 'words' in seg:
                    aligned_seg['words'] = []
                    for word in seg['words']:
                        aligned_word = dict(word)
                        if 'start' in aligned_word:
                            aligned_word['start'] += start_time
                        if 'end' in aligned_word:
                            aligned_word['end'] += start_time
                        aligned_seg['words'].append(aligned_word)
                
                aligned_segments.append(aligned_seg)
                
        except Exception as e:
            logger.error(f"チャンクアライメントエラー: {e}")
            # エラー時は元のセグメントを使用
            for seg in chunk_segments:
                aligned_segments.append({
                    'start': seg['start'] + start_time,
                    'end': seg['end'] + start_time,
                    'text': seg['text']
                })
        
        # プログレス更新
        progress = (chunk_end / len(audio))
        send_progress(progress, f"アライメント処理中... {progress:.1%}")
    
    # 時間順にソート
    aligned_segments.sort(key=lambda x: x['start'])
    
    return aligned_segments


def main():
    """メイン処理"""
    try:
        # コマンドライン引数から設定ファイルパスを取得
        if len(sys.argv) < 2:
            logger.error("設定ファイルパスが指定されていません")
            sys.exit(1)
        
        config_path = sys.argv[1]
        
        if not os.path.exists(config_path):
            logger.error(f"設定ファイルが見つかりません: {config_path}")
            sys.exit(1)
        
        # 設定を読み込み
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        audio_path = config['audio_path']
        api_segments = config['api_segments']
        language = config['language']
        chunk_seconds = config.get('chunk_seconds', 300)
        
        logger.info(f"アライメントワーカー開始: {audio_path}")
        send_progress(0.0, "アライメント処理を開始しています...")
        
        # メモリ使用量を記録
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"初期メモリ使用量: {mem_mb:.1f}MB")
        except:
            pass
        
        # アライメント処理実行
        aligned_segments = process_alignment(
            audio_path,
            api_segments,
            language,
            chunk_seconds
        )
        
        # 結果を保存
        result_data = {
            'segments': aligned_segments,
            'status': 'success'
        }
        
        result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"アライメント完了: {len(aligned_segments)}セグメント")
        send_progress(1.0, "アライメント処理が完了しました")
        
        # 最終メモリ使用量を記録
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"最終メモリ使用量: {mem_mb:.1f}MB")
        except:
            pass
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"アライメントワーカーエラー: {str(e)}", exc_info=True)
        print(f"ERROR:{str(e)}", flush=True)
        
        # エラー結果を保存
        result_data = {
            'segments': [],
            'status': 'error',
            'error': str(e)
        }
        
        result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


if __name__ == "__main__":
    main()