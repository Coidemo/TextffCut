#!/usr/bin/env python3
"""
WhisperXの音声圧縮有無による性能比較テスト

使用方法:
    python test_whisperx_performance.py <動画ファイルパス>
"""

import sys
import time
import tempfile
from pathlib import Path
import subprocess
import json

import whisperx
import torch
import numpy as np
import psutil


def get_memory_info():
    """現在のメモリ使用状況を取得"""
    mem = psutil.virtual_memory()
    return {
        "total_gb": mem.total / (1024**3),
        "available_gb": mem.available / (1024**3),
        "used_gb": mem.used / (1024**3),
        "percent": mem.percent
    }


def compress_audio(video_path: Path, output_path: Path):
    """音声を16kHz/モノラル/16bitに圧縮"""
    cmd = [
        'ffmpeg',
        '-i', str(video_path),
        '-ar', '16000',        # 16kHz
        '-ac', '1',            # モノラル
        '-sample_fmt', 's16',  # 16bit
        '-y',                  # 上書き
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr}")
    
    return output_path


def test_whisperx(audio_path: Path, model_size: str = "large-v3", description: str = ""):
    """WhisperXで文字起こしを実行して性能を測定"""
    print(f"\n{'='*60}")
    print(f"テスト: {description}")
    print(f"音声ファイル: {audio_path}")
    print(f"ファイルサイズ: {audio_path.stat().st_size / (1024**2):.1f} MB")
    print(f"{'='*60}")
    
    # デバイス設定
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    # メモリ情報（開始時）
    mem_start = get_memory_info()
    print(f"\n開始時メモリ: {mem_start['used_gb']:.1f}/{mem_start['total_gb']:.1f} GB ({mem_start['percent']:.1f}%)")
    
    # 音声読み込み
    print("\n音声を読み込み中...")
    load_start = time.time()
    audio = whisperx.load_audio(str(audio_path))
    load_time = time.time() - load_start
    print(f"読み込み時間: {load_time:.1f}秒")
    print(f"音声長: {len(audio) / 16000:.1f}秒")  # 16kHzと仮定
    
    # モデル読み込み
    print("\nモデルを読み込み中...")
    model_start = time.time()
    model = whisperx.load_model(
        model_size,
        device,
        compute_type=compute_type,
        language="ja"
    )
    model_time = time.time() - model_start
    print(f"モデル読み込み時間: {model_time:.1f}秒")
    
    # メモリ情報（モデル読み込み後）
    mem_after_model = get_memory_info()
    print(f"モデル読み込み後メモリ: {mem_after_model['used_gb']:.1f} GB (増加: {mem_after_model['used_gb'] - mem_start['used_gb']:.1f} GB)")
    
    # 文字起こし実行
    print("\n文字起こしを実行中...")
    transcribe_start = time.time()
    
    # バッチサイズを変えてテスト（メモリエラーを避けるため段階的に）
    batch_sizes = [16, 8, 4, 2, 1]
    result = None
    used_batch_size = None
    
    for batch_size in batch_sizes:
        try:
            print(f"バッチサイズ {batch_size} で試行中...")
            result = model.transcribe(
                audio,
                batch_size=batch_size,
                language="ja",
                task="transcribe",
            )
            used_batch_size = batch_size
            print(f"成功！バッチサイズ: {batch_size}")
            break
        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            print(f"バッチサイズ {batch_size} でメモリエラー: {e}")
            if device == "cuda":
                torch.cuda.empty_cache()
            continue
    
    if result is None:
        raise RuntimeError("すべてのバッチサイズで失敗しました")
    
    transcribe_time = time.time() - transcribe_start
    
    # メモリ情報（文字起こし後）
    mem_after_transcribe = get_memory_info()
    peak_memory_increase = mem_after_transcribe['used_gb'] - mem_start['used_gb']
    
    # 結果の統計
    segments = result.get("segments", [])
    total_text_length = sum(len(seg.get("text", "")) for seg in segments)
    
    # 結果サマリー
    summary = {
        "description": description,
        "file_size_mb": audio_path.stat().st_size / (1024**2),
        "audio_duration_sec": len(audio) / 16000,
        "load_time_sec": load_time,
        "model_load_time_sec": model_time,
        "transcribe_time_sec": transcribe_time,
        "total_time_sec": load_time + model_time + transcribe_time,
        "used_batch_size": used_batch_size,
        "num_segments": len(segments),
        "total_text_length": total_text_length,
        "memory_start_gb": mem_start['used_gb'],
        "memory_peak_gb": mem_after_transcribe['used_gb'],
        "memory_increase_gb": peak_memory_increase,
        "device": device,
        "compute_type": compute_type
    }
    
    print(f"\n処理完了！")
    print(f"文字起こし時間: {transcribe_time:.1f}秒")
    print(f"合計時間: {summary['total_time_sec']:.1f}秒")
    print(f"セグメント数: {len(segments)}")
    print(f"メモリ増加: {peak_memory_increase:.1f} GB")
    
    # GPUメモリクリア
    if device == "cuda":
        torch.cuda.empty_cache()
    
    return summary


def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_whisperx_performance.py <動画ファイルパス>")
        sys.exit(1)
    
    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"エラー: ファイルが見つかりません: {video_path}")
        sys.exit(1)
    
    print(f"WhisperX性能比較テスト")
    print(f"動画ファイル: {video_path}")
    print(f"ファイルサイズ: {video_path.stat().st_size / (1024**2):.1f} MB")
    
    results = []
    
    try:
        # テスト1: 元の音声をそのまま使用
        print("\n\n【テスト1: 元の音声（圧縮なし）】")
        result1 = test_whisperx(video_path, description="圧縮なし（元音声）")
        results.append(result1)
        
        # メモリをクリア
        time.sleep(2)
        
        # テスト2: 圧縮した音声を使用
        print("\n\n【テスト2: 圧縮音声（16kHz/モノラル/16bit）】")
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            compressed_path = Path(tmp.name)
        
        print("音声を圧縮中...")
        compress_start = time.time()
        compress_audio(video_path, compressed_path)
        compress_time = time.time() - compress_start
        print(f"圧縮時間: {compress_time:.1f}秒")
        print(f"圧縮後サイズ: {compressed_path.stat().st_size / (1024**2):.1f} MB")
        
        result2 = test_whisperx(compressed_path, description="圧縮あり（16kHz/モノラル）")
        result2['compress_time_sec'] = compress_time
        result2['total_time_with_compress_sec'] = result2['total_time_sec'] + compress_time
        results.append(result2)
        
        # 一時ファイル削除
        compressed_path.unlink()
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    # 結果の比較
    print("\n\n" + "="*80)
    print("【性能比較結果】")
    print("="*80)
    
    if len(results) >= 2:
        r1, r2 = results[0], results[1]
        
        print(f"\n処理時間の比較:")
        print(f"  圧縮なし: {r1['transcribe_time_sec']:.1f}秒")
        print(f"  圧縮あり: {r2['transcribe_time_sec']:.1f}秒 (圧縮時間含む: {r2['total_time_with_compress_sec']:.1f}秒)")
        print(f"  速度比: {r1['transcribe_time_sec'] / r2['transcribe_time_sec']:.2f}x")
        
        print(f"\nメモリ使用量の比較:")
        print(f"  圧縮なし: {r1['memory_increase_gb']:.1f} GB増加")
        print(f"  圧縮あり: {r2['memory_increase_gb']:.1f} GB増加")
        print(f"  削減率: {(1 - r2['memory_increase_gb'] / r1['memory_increase_gb']) * 100:.1f}%")
        
        print(f"\nファイルサイズ:")
        print(f"  元ファイル: {r1['file_size_mb']:.1f} MB")
        print(f"  圧縮後: {r2['file_size_mb']:.1f} MB")
        print(f"  削減率: {(1 - r2['file_size_mb'] / r1['file_size_mb']) * 100:.1f}%")
    
    # JSON形式で結果を保存
    output_path = Path("whisperx_performance_comparison.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n結果をJSON形式で保存: {output_path}")


if __name__ == "__main__":
    main()