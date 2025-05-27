"""
文字起こし機能のモジュール
"""

import os
import json
import whisper
import streamlit as st
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from ..config import config
from ..utils import BuzzClipError

def load_whisper_model(model_name: str) -> whisper.Whisper:
    """Whisperモデルを読み込む"""
    try:
        return whisper.load_model(model_name)
    except Exception as e:
        raise BuzzClipError(f"Whisperモデルの読み込みに失敗: {str(e)}")

def transcribe_video(video_path: str, model_name: str = "large-v3") -> Dict[str, Any]:
    """動画を文字起こしする"""
    try:
        # モデルの読み込み
        model = load_whisper_model(model_name)
        
        # 文字起こしの実行
        result = model.transcribe(
            video_path,
            language="ja",
            verbose=False
        )
        
        return result
    except Exception as e:
        raise BuzzClipError(f"文字起こしに失敗: {str(e)}")

def save_transcription(result: Dict[str, Any], video_path: str, model_name: str) -> Path:
    """文字起こし結果を保存"""
    try:
        # 出力ファイル名の生成
        video_name = Path(video_path).stem
        output_path = config.transcriptions_dir / f"{video_name}_{model_name}.json"
        
        # JSONファイルとして保存
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return output_path
    except Exception as e:
        raise BuzzClipError(f"文字起こし結果の保存に失敗: {str(e)}")

def load_transcription(video_path: str, model_name: str) -> Optional[Dict[str, Any]]:
    """保存済みの文字起こし結果を読み込む"""
    try:
        # ファイル名の生成
        video_name = Path(video_path).stem
        file_path = config.transcriptions_dir / f"{video_name}_{model_name}.json"
        
        # ファイルが存在しない場合はNoneを返す
        if not file_path.exists():
            return None
        
        # JSONファイルを読み込む
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise BuzzClipError(f"文字起こし結果の読み込みに失敗: {str(e)}")

def get_transcription_text(result: Dict[str, Any]) -> str:
    """文字起こし結果からテキストを抽出"""
    try:
        return result["text"]
    except KeyError:
        raise BuzzClipError("文字起こし結果からテキストを抽出できません")

def get_transcription_segments(result: Dict[str, Any]) -> list:
    """文字起こし結果からセグメント情報を抽出"""
    try:
        return result["segments"]
    except KeyError:
        raise BuzzClipError("文字起こし結果からセグメント情報を抽出できません") 