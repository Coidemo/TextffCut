"""
TextffCut Desktop API Server
FastAPIを使用したバックエンドサーバー
"""
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import sys
import asyncio
from typing import Optional, List, Tuple
import tempfile
import shutil
import subprocess

# 親ディレクトリのモジュールをインポート
sys.path.append(str(Path(__file__).parent.parent))

from utils.logging import get_logger

logger = get_logger(__name__)

from core.transcription import Transcriber
from core.text_processor import TextProcessor
from core.video import VideoProcessor, VideoInfo
from core.export import FCPXMLExporter, EDLExporter, ExportSegment
from config import config

app = FastAPI(title="TextffCut API", version="1.0.0")

# CORS設定（Electronからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "file://"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエスト/レスポンスモデル
class TranscriptionRequest(BaseModel):
    video_path: str
    model_size: str = "large-v3"
    
class ProcessRequest(BaseModel):
    video_path: str
    original_text: str
    edited_text: str
    transcription_segments: Optional[List[dict]] = None  # 文字起こしセグメント情報
    remove_silence: bool = False
    noise_threshold: float = -35.0
    min_silence_duration: float = 0.3
    min_segment_duration: float = 0.3
    padding_start: float = 0.1
    padding_end: float = 0.1
    output_video: bool = False  # 動画ファイルも出力するかどうか
    
class ProgressResponse(BaseModel):
    status: str
    progress: float
    message: str

# グローバル状態管理
current_tasks = {}

class ProgressTracker:
    """プログレス追跡クラス"""
    def __init__(self):
        self.tasks = {}
    
    def start_task(self, task_id: str, total_steps: int = 100):
        """タスク開始"""
        self.tasks[task_id] = {
            "progress": 0,
            "total_steps": total_steps,
            "current_step": 0,
            "message": "開始中...",
            "status": "running"
        }
    
    def update_progress(self, task_id: str, step: int, message: str = ""):
        """プログレス更新"""
        if task_id in self.tasks:
            self.tasks[task_id]["current_step"] = step
            self.tasks[task_id]["progress"] = min(100, (step / self.tasks[task_id]["total_steps"]) * 100)
            if message:
                self.tasks[task_id]["message"] = message
    
    def complete_task(self, task_id: str, message: str = "完了"):
        """タスク完了"""
        if task_id in self.tasks:
            self.tasks[task_id]["progress"] = 100
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["message"] = message
    
    def error_task(self, task_id: str, message: str = "エラー"):
        """タスクエラー"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "error"
            self.tasks[task_id]["message"] = message
    
    def get_progress(self, task_id: str):
        """プログレス取得"""
        return self.tasks.get(task_id, None)
    
    def remove_task(self, task_id: str):
        """タスク削除"""
        if task_id in self.tasks:
            del self.tasks[task_id]

progress_tracker = ProgressTracker()

def extract_time_ranges_from_segments(original_text: str, edited_text: str, segments: List[dict]) -> List[Tuple[float, float]]:
    """
    セグメント情報を使って編集されたテキストの時間範囲を抽出
    
    Args:
        original_text: 元のテキスト
        edited_text: 編集されたテキスト
        segments: 文字起こしセグメント情報
        
    Returns:
        時間範囲のリスト [(start, end), ...]
    """
    if not edited_text.strip():
        return []
    
    # 編集されたテキストの単語を取得
    edited_words = [word.strip() for word in edited_text.split() if word.strip()]
    if not edited_words:
        return []
    
    # セグメントから該当する時間範囲を探す
    time_ranges = []
    for segment in segments:
        segment_text = segment.get('text', '')
        segment_start = segment.get('start', 0.0)
        segment_end = segment.get('end', 0.0)
        
        # 編集されたテキストの単語がこのセグメントに含まれているかチェック
        for word in edited_words:
            if word in segment_text:
                # 既に追加された範囲と重複チェック
                overlapping = False
                for existing_start, existing_end in time_ranges:
                    if (segment_start < existing_end and segment_end > existing_start):
                        # 重複する場合は範囲を拡張
                        time_ranges.remove((existing_start, existing_end))
                        time_ranges.append((
                            min(existing_start, segment_start),
                            max(existing_end, segment_end)
                        ))
                        overlapping = True
                        break
                
                if not overlapping:
                    time_ranges.append((segment_start, segment_end))
                break
    
    # 時間順にソート
    time_ranges.sort(key=lambda x: x[0])
    return time_ranges

def combine_video_segments(video_files: List[str], output_path: str) -> bool:
    """
    複数の動画セグメントを結合
    
    Args:
        video_files: 結合する動画ファイルのリスト
        output_path: 出力ファイルパス
        
    Returns:
        成功したかどうか
    """
    try:
        # 一時的なリストファイルを作成
        list_file = Path(output_path).parent / "concat_list.txt"
        with open(list_file, 'w') as f:
            for video_file in video_files:
                f.write(f"file '{video_file}'\n")
        
        # FFmpegで結合
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 一時ファイル削除
        if list_file.exists():
            list_file.unlink()
        
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"動画結合エラー: {e}")
        return False

@app.get("/")
def read_root():
    return {"message": "TextffCut API Server", "version": "1.0.0"}

@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """タスクのプログレス状況を取得"""
    progress = progress_tracker.get_progress(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress

@app.get("/api/transcribe/cache-status/{video_name}/{model_size}")
async def check_transcription_cache(video_name: str, model_size: str):
    """文字起こしキャッシュの存在確認"""
    try:
        transcriber = Transcriber(config)
        # 仮のパスでキャッシュパスを生成
        temp_path = f"/temp/{video_name}.mp4"
        cache_path = transcriber.get_cache_path(temp_path, model_size)
        
        has_cache = cache_path.exists()
        
        return {
            "has_cache": has_cache,
            "cache_path": str(cache_path) if has_cache else None,
            "video_name": video_name,
            "model_size": model_size
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe/from-cache")
async def load_transcription_from_cache(request: dict):
    """キャッシュから文字起こし結果を読み込み"""
    try:
        video_name = request.get("video_name")
        model_size = request.get("model_size")
        
        if not video_name or not model_size:
            raise HTTPException(status_code=400, detail="video_name and model_size are required")
        
        transcriber = Transcriber(config)
        temp_path = f"/temp/{video_name}.mp4"
        cache_path = transcriber.get_cache_path(temp_path, model_size)
        
        result = transcriber.load_from_cache(cache_path)
        if not result:
            raise HTTPException(status_code=404, detail="Cache not found")
        
        full_text = result.get_full_text()
        
        return {
            "success": True,
            "text": full_text,
            "segments": [seg.__dict__ for seg in result.segments],
            "message": "キャッシュから文字起こし結果を読み込みました",
            "from_cache": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def transcribe_video(request: TranscriptionRequest):
    """動画の文字起こし実行"""
    try:
        video_path = Path(request.video_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # タスクIDを生成
        import uuid
        task_id = str(uuid.uuid4())
        
        # プログレス開始
        progress_tracker.start_task(task_id, 100)
        progress_tracker.update_progress(task_id, 10, "文字起こしを開始しています...")
        
        # 文字起こし処理
        transcriber = Transcriber(config)
        
        # プログレス付きで文字起こし実行
        async def transcribe_with_progress():
            progress_tracker.update_progress(task_id, 20, "音声を解析中...")
            
            result = await asyncio.to_thread(
                transcriber.transcribe,
                str(video_path),
                model_size=request.model_size
            )
            
            progress_tracker.update_progress(task_id, 90, "結果を処理中...")
            return result
        
        result = await transcribe_with_progress()
        
        # テキスト生成
        full_text = result.get_full_text()
        
        progress_tracker.complete_task(task_id, "文字起こしが完了しました")
        
        return {
            "success": True,
            "text": full_text,
            "segments": [seg.__dict__ for seg in result.segments],
            "message": "文字起こしが完了しました",
            "task_id": task_id
        }
        
    except HTTPException:
        # HTTPExceptionはそのまま再発生
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "ファイルが見つかりません")
        raise
    except FileNotFoundError as e:
        # ファイルが見つからない場合は404
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "ファイルが見つかりません")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")
    except PermissionError as e:
        # 権限エラーの場合は403
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "ファイルアクセス権限がありません")
        raise HTTPException(status_code=403, detail=f"Permission denied: {str(e)}")
    except Exception as e:
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process")
async def process_video(request: ProcessRequest):
    """動画処理（切り抜き・無音削除）実行"""
    try:
        video_path = Path(request.video_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        if not video_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        # ファイルアクセス権限をチェック
        try:
            video_path.stat()
        except PermissionError:
            raise HTTPException(status_code=403, detail="Permission denied to access file")
        
        # タスクIDを生成
        import uuid
        task_id = str(uuid.uuid4())
        
        # プログレス開始
        progress_tracker.start_task(task_id, 100)
        progress_tracker.update_progress(task_id, 10, "処理を開始しています...")
        
        # テキスト差分から時間範囲を取得（セパレータ対応）
        progress_tracker.update_progress(task_id, 20, "テキスト差分を解析中...")
        text_processor = TextProcessor()
        
        # セパレータパターンをチェック
        separator_patterns = ["---", "——", "－－－"]
        found_separator = None
        
        for pattern in separator_patterns:
            if pattern in request.edited_text:
                found_separator = pattern
                break
        
        # transcription_segmentsが提供されている場合はセグメント情報を使用
        if request.transcription_segments:
            from core.transcription import TranscriptionResult, TranscriptionSegment
            
            # セグメント情報からTranscriptionResultを再構築
            segments = []
            for seg_data in request.transcription_segments:
                segment = TranscriptionSegment(
                    start=seg_data.get('start', 0.0),
                    end=seg_data.get('end', 0.0),
                    text=seg_data.get('text', ''),
                    words=seg_data.get('words', [])
                )
                segments.append(segment)
            
            transcription_result = TranscriptionResult(
                language="ja",
                segments=segments,
                original_audio_path=request.video_path,
                model_size="unknown",
                processing_time=0.0
            )
            
            if found_separator:
                # セパレータがある場合：セパレータ対応の差分検索
                time_ranges = text_processor.find_differences_with_separator(
                    request.original_text,
                    request.edited_text,
                    transcription_result,
                    found_separator
                )
            else:
                # セパレータがない場合：通常の差分検索
                diff = text_processor.find_differences(
                    request.original_text,
                    request.edited_text
                )
                time_ranges = diff.get_time_ranges(transcription_result)
        else:
            # セグメント情報がない場合は固定値
            if found_separator:
                # セパレータがある場合：複数セクションを想定した固定値
                sections = text_processor.split_text_by_separator(request.edited_text, found_separator)
                time_ranges = [(i * 10.0, (i + 1) * 10.0) for i in range(len(sections))]
            else:
                # 単一セクション
                time_ranges = [(0.0, 10.0)]
        
        # エラー検証：編集テキストに元の動画に存在しない文字が含まれているかチェック
        has_additions = False
        error_sections = []
        
        if found_separator and request.transcription_segments:
            # セパレータがある場合：各セクションで追加文字をチェック
            sections = text_processor.split_text_by_separator(request.edited_text, found_separator)
            for i, section in enumerate(sections):
                diff = text_processor.find_differences(request.original_text, section)
                if diff.has_additions():
                    has_additions = True
                    error_sections.append(i + 1)
        elif request.transcription_segments:
            # セパレータがない場合：通常のチェック
            diff = text_processor.find_differences(request.original_text, request.edited_text)
            if diff.has_additions():
                has_additions = True
        
        if has_additions:
            error_message = "元の動画に存在しない文字が含まれています。"
            if error_sections:
                error_message += f" 問題のセクション: {', '.join(map(str, error_sections))}"
            return {
                "success": False,
                "message": error_message,
                "error_type": "invalid_characters",
                "error_sections": error_sections
            }
        
        if not time_ranges:
            return {
                "success": False,
                "message": "変更が検出されませんでした"
            }
        
        # 出力ディレクトリ作成
        output_dir = video_path.parent / "output" / f"{video_path.stem}_processed"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 動画処理
        progress_tracker.update_progress(task_id, 30, "動画情報を取得中...")
        video_processor = VideoProcessor(config)
        
        # 動画情報を取得
        video_info = VideoInfo.from_file(str(video_path))
        
        if request.remove_silence:
            # 無音削除処理
            progress_tracker.update_progress(task_id, 40, "無音部分を検出中...")
            keep_ranges = video_processor.remove_silence_new(
                str(video_path),  # input_path引数を追加
                time_ranges,
                str(output_dir),  # output_dir引数を追加
                noise_threshold=request.noise_threshold,
                min_silence_duration=request.min_silence_duration,
                min_segment_duration=request.min_segment_duration,
                padding_start=request.padding_start,
                padding_end=request.padding_end
            )
            progress_tracker.update_progress(task_id, 60, "無音削除処理完了")
        else:
            keep_ranges = time_ranges
            progress_tracker.update_progress(task_id, 50, "時間範囲を確定")
        
        # FCPXML出力
        progress_tracker.update_progress(task_id, 70, "FCPXMLファイルを生成中...")
        fcpxml_path = output_dir / f"{video_path.stem}.fcpxml"
        exporter = FCPXMLExporter(config)
        
        # 時間範囲をExportSegmentに変換
        segments = []
        timeline_start = 0.0
        for start, end in keep_ranges:
            segment = ExportSegment(
                source_path=str(video_path),
                start_time=start,
                end_time=end,
                timeline_start=timeline_start
            )
            segments.append(segment)
            timeline_start += (end - start)
        
        exporter.export(
            segments,
            str(fcpxml_path),
            int(video_info.fps),
            f"{video_path.stem}_processed"
        )
        
        result = {
            "success": True,
            "message": "処理が完了しました",
            "output_dir": str(output_dir),
            "fcpxml_path": str(fcpxml_path),
            "time_ranges": time_ranges,
            "keep_ranges": keep_ranges
        }
        
        # 動画出力が要求されている場合
        if request.output_video:
            progress_tracker.update_progress(task_id, 80, "動画セグメントを抽出中...")
            video_files = []
            for i, (start, end) in enumerate(keep_ranges):
                segment_path = output_dir / f"segment_{i+1}.mp4"
                progress_tracker.update_progress(task_id, 80 + (i+1) * 5, f"セグメント {i+1} を抽出中...")
                success = video_processor.extract_segment(
                    str(video_path),
                    start,
                    end,
                    str(segment_path)
                )
                if success:
                    video_files.append(str(segment_path))
            
            # 複数セグメントがある場合は結合
            if len(video_files) > 1:
                progress_tracker.update_progress(task_id, 95, "動画セグメントを結合中...")
                combined_path = output_dir / "combined.mp4"
                success = combine_video_segments(video_files, str(combined_path))
                if success:
                    result["video_path"] = str(combined_path)
                    result["segment_files"] = video_files
                else:
                    result["video_path"] = video_files[0] if video_files else None
                    result["segment_files"] = video_files
            elif video_files:
                result["video_path"] = video_files[0]
                result["segment_files"] = video_files
        
        # タスク完了
        progress_tracker.complete_task(task_id, "処理が完了しました")
        result["task_id"] = task_id
        
        return result
        
    except HTTPException:
        # HTTPExceptionはそのまま再発生
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "リクエストエラー")
        raise
    except FileNotFoundError as e:
        # ファイルが見つからない場合は404
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "ファイルが見つかりません")
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")
    except PermissionError as e:
        # 権限エラーの場合は403
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, "ファイルアクセス権限がありません")
        raise HTTPException(status_code=403, detail=f"Permission denied: {str(e)}")
    except Exception as e:
        if 'task_id' in locals():
            progress_tracker.error_task(task_id, f"エラー: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
def get_settings():
    """アプリケーション設定を取得"""
    return {
        "whisper_models": config.transcription.whisper_models,
        "supported_formats": config.video.supported_formats,
        "default_noise_threshold": config.video.default_noise_threshold,
        "default_min_silence_duration": config.video.default_min_silence_duration,
        "default_min_segment_duration": config.video.default_min_segment_duration,
        "default_padding_start": config.video.default_padding_start,
        "default_padding_end": config.video.default_padding_end,
        "separator_patterns": ["---", "——", "－－－"]  # セパレータパターンを追加
    }

@app.post("/api/text/validate")
async def validate_text(request: dict):
    """テキストの検証（セパレータ対応・エラー検出）"""
    try:
        original_text = request.get("original_text", "")
        edited_text = request.get("edited_text", "")
        transcription_segments = request.get("transcription_segments", [])
        
        if not original_text or not edited_text:
            raise HTTPException(status_code=400, detail="original_text and edited_text are required")
        
        text_processor = TextProcessor()
        
        # セパレータパターンをチェック
        separator_patterns = ["---", "——", "－－－"]
        found_separator = None
        
        for pattern in separator_patterns:
            if pattern in edited_text:
                found_separator = pattern
                break
        
        # エラー検証
        has_additions = False
        error_sections = []
        sections_info = []
        
        if found_separator:
            # セパレータがある場合：各セクションをチェック
            sections = text_processor.split_text_by_separator(edited_text, found_separator)
            
            for i, section in enumerate(sections):
                diff = text_processor.find_differences(original_text, section)
                section_info = {
                    "section_number": i + 1,
                    "text": section,
                    "character_count": len(section),
                    "has_errors": diff.has_additions(),
                    "added_characters": list(diff.added_chars) if diff.has_additions() else []
                }
                sections_info.append(section_info)
                
                if diff.has_additions():
                    has_additions = True
                    error_sections.append(i + 1)
        else:
            # セパレータがない場合：通常のチェック
            diff = text_processor.find_differences(original_text, edited_text)
            if diff.has_additions():
                has_additions = True
            
            sections_info = [{
                "section_number": 1,
                "text": edited_text,
                "character_count": len(edited_text),
                "has_errors": diff.has_additions(),
                "added_characters": list(diff.added_chars) if diff.has_additions() else []
            }]
        
        return {
            "success": True,
            "has_separator": found_separator is not None,
            "separator_used": found_separator,
            "total_sections": len(sections_info),
            "has_errors": has_additions,
            "error_sections": error_sections,
            "sections": sections_info,
            "total_characters": len(edited_text),
            "validation_passed": not has_additions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """ファイルアップロード処理"""
    try:
        # 一時ファイルに保存
        temp_dir = Path(tempfile.gettempdir()) / "textffcut"
        temp_dir.mkdir(exist_ok=True)
        
        file_path = temp_dir / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        return {
            "success": True,
            "file_path": str(file_path),
            "filename": file.filename
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)