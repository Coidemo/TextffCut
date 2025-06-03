"""
WhisperXアライメント処理のラッパー
transformersライブラリのバージョン互換性問題を解決
"""
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)

def safe_load_align_model(language_code: str, device: str = "cpu") -> Tuple[Optional[Any], Optional[Any]]:
    """
    アライメントモデルを安全に読み込む
    
    Returns:
        (align_model, align_metadata) or (None, None) if failed
    """
    try:
        import whisperx
        
        # WhisperXのアライメントモデルを読み込み
        align_model, align_metadata = whisperx.load_align_model(
            language_code=language_code,
            device=device
        )
        
        # transformersのバージョン互換性修正
        if hasattr(align_model, 'processor') and hasattr(align_model.processor, 'feature_extractor'):
            # 新しいバージョンの場合
            if not hasattr(align_model.processor, 'sampling_rate'):
                # sampling_rateをfeature_extractorから取得して設定
                if hasattr(align_model.processor.feature_extractor, 'sampling_rate'):
                    align_model.processor.sampling_rate = align_model.processor.feature_extractor.sampling_rate
                else:
                    # デフォルト値を設定
                    align_model.processor.sampling_rate = 16000
                    logger.warning("sampling_rateが見つからないため、デフォルト値16000を使用")
        
        logger.info(f"アライメントモデルを読み込みました: {language_code}")
        return align_model, align_metadata
        
    except ImportError as e:
        logger.warning(f"WhisperXが利用できません: {e}")
        return None, None
    except Exception as e:
        logger.error(f"アライメントモデルの読み込みに失敗: {e}")
        return None, None


def safe_align_segments(
    segments: List[Dict[str, Any]], 
    align_model: Any, 
    align_metadata: Any,
    audio: np.ndarray,
    device: str = "cpu",
    return_char_alignments: bool = True
) -> Optional[Dict[str, Any]]:
    """
    セグメントを安全にアライメント処理
    
    Args:
        segments: アライメントするセグメントのリスト
        align_model: アライメントモデル
        align_metadata: アライメントメタデータ
        audio: 音声データ（numpy array）
        device: 使用するデバイス
        return_char_alignments: 文字レベルのアライメントを返すか
        
    Returns:
        アライメント結果 or None if failed
    """
    try:
        import whisperx
        
        # セグメントが空の場合は処理しない
        if not segments:
            logger.warning("アライメント対象のセグメントが空です")
            return {"segments": []}
        
        # 音声データの検証
        if audio is None or len(audio) == 0:
            logger.warning("音声データが無効です")
            return {"segments": segments}
        
        # アライメント実行前にモデルの状態を確認
        if hasattr(align_model, 'processor'):
            processor = align_model.processor
            
            # sampling_rateの確認と修正
            if not hasattr(processor, 'sampling_rate'):
                if hasattr(processor, 'feature_extractor') and hasattr(processor.feature_extractor, 'sampling_rate'):
                    processor.sampling_rate = processor.feature_extractor.sampling_rate
                else:
                    processor.sampling_rate = 16000
                    
            logger.debug(f"アライメント実行: sampling_rate={getattr(processor, 'sampling_rate', 'unknown')}")
        
        # アライメント実行
        try:
            result = whisperx.align(
                segments,
                align_model,
                align_metadata,
                audio,
                device,
                return_char_alignments=return_char_alignments
            )
            
            # 結果の検証
            if result and "segments" in result:
                logger.debug(f"アライメント成功: {len(result['segments'])}セグメント")
                return result
            else:
                logger.warning("アライメント結果が不正です")
                return {"segments": segments}
                
        except RuntimeError as e:
            if "CUDA" in str(e) or "memory" in str(e):
                logger.warning(f"メモリ不足でアライメント失敗: {e}")
                # CPUで再試行
                if device != "cpu":
                    logger.info("CPUモードで再試行します")
                    return safe_align_segments(
                        segments, align_model, align_metadata, 
                        audio, "cpu", return_char_alignments
                    )
            else:
                logger.warning(f"ランタイムエラー: {e}")
            return {"segments": segments}
            
    except AttributeError as e:
        logger.error(f"属性エラー（transformersバージョン互換性問題の可能性）: {e}")
        # エラー詳細をログ
        if align_model and hasattr(align_model, 'processor'):
            processor = align_model.processor
            logger.debug(f"Processor type: {type(processor)}")
            logger.debug(f"Processor attributes: {dir(processor)}")
        return {"segments": segments}
        
    except Exception as e:
        logger.error(f"アライメント処理で予期しないエラー: {type(e).__name__}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return {"segments": segments}


def validate_segments_for_alignment(segments: List[Dict[str, Any]], audio_duration: float) -> List[Dict[str, Any]]:
    """
    アライメント前にセグメントを検証・修正
    
    Args:
        segments: 検証するセグメント
        audio_duration: 音声の長さ（秒）
        
    Returns:
        修正されたセグメントリスト
    """
    validated_segments = []
    
    for seg in segments:
        # 必須フィールドの確認
        if "start" not in seg or "end" not in seg or "text" not in seg:
            logger.warning(f"不正なセグメント（必須フィールド不足）: {seg}")
            continue
            
        # タイムスタンプの検証
        start = float(seg["start"])
        end = float(seg["end"])
        
        # 開始時刻が音声長を超えている場合
        if start >= audio_duration:
            logger.warning(f"セグメント開始時刻が音声長を超過: start={start}, duration={audio_duration}")
            continue
            
        # 終了時刻が音声長を超えている場合は修正
        if end > audio_duration:
            logger.warning(f"セグメント終了時刻を修正: {end} -> {audio_duration}")
            seg = seg.copy()
            seg["end"] = audio_duration
            
        # 開始時刻が終了時刻より後の場合
        if start >= end:
            logger.warning(f"不正なセグメント時刻: start={start}, end={end}")
            continue
            
        # テキストが空の場合
        if not seg["text"].strip():
            logger.warning("空のテキストセグメントをスキップ")
            continue
            
        validated_segments.append(seg)
    
    return validated_segments