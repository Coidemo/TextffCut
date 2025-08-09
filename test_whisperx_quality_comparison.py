#!/usr/bin/env python3
"""
WhisperXの音声圧縮有無による品質比較テスト

使用方法:
    python test_whisperx_quality_comparison.py <動画ファイルパス>
"""

import sys
import time
import tempfile
from pathlib import Path
import subprocess
import json
import difflib
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

import whisperx
import torch
import numpy as np


@dataclass
class AlignmentInfo:
    """アライメント情報の統計"""
    total_words: int
    aligned_words: int
    alignment_rate: float
    avg_confidence: float
    low_confidence_words: List[Dict[str, Any]]
    
    
def compress_audio(video_path: Path, output_path: Path) -> Path:
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


def analyze_alignment(segments: List[Dict]) -> AlignmentInfo:
    """アライメント情報を分析"""
    total_words = 0
    aligned_words = 0
    confidence_scores = []
    low_confidence_words = []
    
    for segment in segments:
        words = segment.get('words', [])
        for word in words:
            total_words += 1
            
            # アライメントされているか確認
            if 'start' in word and 'end' in word:
                aligned_words += 1
                
                # 信頼度スコアを収集
                confidence = word.get('score', word.get('confidence', 0))
                if confidence:
                    confidence_scores.append(confidence)
                    
                    # 低信頼度の単語を記録
                    if confidence < 0.5:
                        low_confidence_words.append({
                            'word': word.get('word', ''),
                            'confidence': confidence,
                            'start': word.get('start', 0),
                            'end': word.get('end', 0)
                        })
    
    alignment_rate = aligned_words / total_words if total_words > 0 else 0
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
    
    return AlignmentInfo(
        total_words=total_words,
        aligned_words=aligned_words,
        alignment_rate=alignment_rate,
        avg_confidence=avg_confidence,
        low_confidence_words=low_confidence_words[:10]  # 最初の10個のみ
    )


def compare_transcriptions(result1: Dict, result2: Dict) -> Dict[str, Any]:
    """2つの文字起こし結果を比較"""
    segments1 = result1.get('segments', [])
    segments2 = result2.get('segments', [])
    
    # テキストの抽出
    text1 = ' '.join(seg.get('text', '').strip() for seg in segments1)
    text2 = ' '.join(seg.get('text', '').strip() for seg in segments2)
    
    # 文字レベルの差分
    char_diff = difflib.SequenceMatcher(None, text1, text2)
    char_similarity = char_diff.ratio()
    
    # 単語レベルの差分
    words1 = text1.split()
    words2 = text2.split()
    word_diff = difflib.SequenceMatcher(None, words1, words2)
    word_similarity = word_diff.ratio()
    
    # 差分の詳細
    char_opcodes = char_diff.get_opcodes()
    differences = []
    for tag, i1, i2, j1, j2 in char_opcodes:
        if tag != 'equal':
            differences.append({
                'type': tag,
                'text1': text1[i1:i2],
                'text2': text2[j1:j2],
                'position': i1
            })
    
    # アライメント情報の分析
    alignment1 = analyze_alignment(segments1)
    alignment2 = analyze_alignment(segments2)
    
    return {
        'text_length': {
            'original': len(text1),
            'compressed': len(text2)
        },
        'word_count': {
            'original': len(words1),
            'compressed': len(words2)
        },
        'similarity': {
            'character_level': char_similarity,
            'word_level': word_similarity
        },
        'differences': differences[:10],  # 最初の10個の差分
        'alignment': {
            'original': {
                'total_words': alignment1.total_words,
                'aligned_words': alignment1.aligned_words,
                'alignment_rate': alignment1.alignment_rate,
                'avg_confidence': alignment1.avg_confidence,
                'low_confidence_count': len(alignment1.low_confidence_words)
            },
            'compressed': {
                'total_words': alignment2.total_words,
                'aligned_words': alignment2.aligned_words,
                'alignment_rate': alignment2.alignment_rate,
                'avg_confidence': alignment2.avg_confidence,
                'low_confidence_count': len(alignment2.low_confidence_words)
            }
        }
    }


def transcribe_with_alignment(audio_path: Path, model_size: str = "large-v3") -> Tuple[Dict, float]:
    """WhisperXで文字起こしとアライメントを実行"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"処理中: {audio_path.name}")
    start_time = time.time()
    
    # 音声読み込み
    audio = whisperx.load_audio(str(audio_path))
    
    # モデル読み込みと文字起こし
    model = whisperx.load_model(
        model_size,
        device,
        compute_type=compute_type,
        language="ja"
    )
    
    result = model.transcribe(
        audio,
        batch_size=8,
        language="ja",
        task="transcribe",
    )
    
    # アライメント
    try:
        print("アライメント処理中...")
        align_model, metadata = whisperx.load_align_model(
            language_code="ja",
            device=device
        )
        
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=True
        )
    except Exception as e:
        print(f"アライメントエラー: {e}")
        # アライメントなしで続行
    
    processing_time = time.time() - start_time
    
    # GPUメモリクリア
    if device == "cuda":
        torch.cuda.empty_cache()
    
    return result, processing_time


def save_detailed_results(result: Dict, output_path: Path):
    """詳細な結果をテキストファイルに保存"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=== 文字起こし結果 ===\n\n")
        
        for i, segment in enumerate(result.get('segments', [])):
            f.write(f"セグメント {i+1}:\n")
            f.write(f"時間: {segment.get('start', 0):.2f} - {segment.get('end', 0):.2f}\n")
            f.write(f"テキスト: {segment.get('text', '')}\n")
            
            # 単語レベルの情報
            words = segment.get('words', [])
            if words:
                f.write("単語:\n")
                for word in words:
                    w = word.get('word', '')
                    start = word.get('start', 'N/A')
                    end = word.get('end', 'N/A')
                    conf = word.get('score', word.get('confidence', 'N/A'))
                    f.write(f"  - {w} [{start}-{end}] (信頼度: {conf})\n")
            
            f.write("\n")


def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_whisperx_quality_comparison.py <動画ファイルパス>")
        sys.exit(1)
    
    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"エラー: ファイルが見つかりません: {video_path}")
        sys.exit(1)
    
    print(f"WhisperX品質比較テスト")
    print(f"動画ファイル: {video_path}")
    print("="*80)
    
    try:
        # 1. 元の音声で文字起こし
        print("\n【元の音声で文字起こし】")
        result1, time1 = transcribe_with_alignment(video_path)
        save_detailed_results(result1, Path("transcription_original.txt"))
        print(f"処理時間: {time1:.1f}秒")
        
        # 2. 圧縮音声で文字起こし
        print("\n【圧縮音声で文字起こし】")
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            compressed_path = Path(tmp.name)
        
        compress_audio(video_path, compressed_path)
        result2, time2 = transcribe_with_alignment(compressed_path)
        save_detailed_results(result2, Path("transcription_compressed.txt"))
        print(f"処理時間: {time2:.1f}秒")
        
        # 圧縮ファイル削除
        compressed_path.unlink()
        
        # 3. 結果の比較
        print("\n【品質比較】")
        comparison = compare_transcriptions(result1, result2)
        
        print(f"\n文字数:")
        print(f"  元音声: {comparison['text_length']['original']}文字")
        print(f"  圧縮音声: {comparison['text_length']['compressed']}文字")
        
        print(f"\n単語数:")
        print(f"  元音声: {comparison['word_count']['original']}単語")
        print(f"  圧縮音声: {comparison['word_count']['compressed']}単語")
        
        print(f"\n類似度:")
        print(f"  文字レベル: {comparison['similarity']['character_level']:.1%}")
        print(f"  単語レベル: {comparison['similarity']['word_level']:.1%}")
        
        print(f"\nアライメント品質:")
        orig_align = comparison['alignment']['original']
        comp_align = comparison['alignment']['compressed']
        
        print(f"  元音声:")
        print(f"    - アライメント率: {orig_align['alignment_rate']:.1%} ({orig_align['aligned_words']}/{orig_align['total_words']})")
        print(f"    - 平均信頼度: {orig_align['avg_confidence']:.3f}")
        print(f"    - 低信頼度単語数: {orig_align['low_confidence_count']}")
        
        print(f"  圧縮音声:")
        print(f"    - アライメント率: {comp_align['alignment_rate']:.1%} ({comp_align['aligned_words']}/{comp_align['total_words']})")
        print(f"    - 平均信頼度: {comp_align['avg_confidence']:.3f}")
        print(f"    - 低信頼度単語数: {comp_align['low_confidence_count']}")
        
        # 主な差分を表示
        if comparison['differences']:
            print(f"\n主な差分（最初の5個）:")
            for i, diff in enumerate(comparison['differences'][:5]):
                print(f"  {i+1}. 位置{diff['position']}: '{diff['text1']}' → '{diff['text2']}'")
        
        # 結果をJSONに保存
        with open("quality_comparison_result.json", 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        
        print(f"\n詳細な結果を以下に保存しました:")
        print(f"  - transcription_original.txt")
        print(f"  - transcription_compressed.txt")
        print(f"  - quality_comparison_result.json")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()