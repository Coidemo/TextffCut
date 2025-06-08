"""
文字起こしサービス

文字起こし処理のビジネスロジックを提供。
キャッシュ管理、モデル選択、API/ローカル切り替えなどを統合的に管理。
"""

from typing import Optional, List, Dict, Callable
from pathlib import Path
import hashlib
import json

from .base import BaseService, ServiceResult, ValidationError, ProcessingError
from config import Config
from core import Transcriber
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription_subprocess import SubprocessTranscriber
from core.models import TranscriptionResult, TranscriptionResultV2
from core.constants import MemoryEstimates, ErrorMessages
from utils.file_utils import ensure_directory


class TranscriptionService(BaseService):
    """文字起こし処理のビジネスロジック
    
    責任:
    - 適切なTranscriberの選択
    - キャッシュの管理
    - プログレス通知
    - エラーハンドリング
    """
    
    def _initialize(self):
        """サービス固有の初期化"""
        self.cache_dir = Path("transcriptions")
        ensure_directory(self.cache_dir)
    
    def execute(
        self, 
        video_path: str,
        model_size: str,
        use_api: bool = False,
        api_key: Optional[str] = None,
        use_cache: bool = True,
        save_cache: bool = True,
        language: str = "ja",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        separated_mode: bool = False,
        task_type: str = "full"
    ) -> ServiceResult:
        """文字起こしを実行
        
        Args:
            video_path: 動画ファイルパス
            model_size: モデルサイズ（base, small, medium, large-v3）
            use_api: API使用フラグ
            api_key: APIキー（API使用時）
            use_cache: キャッシュ使用フラグ
            save_cache: キャッシュ保存フラグ
            language: 言語コード
            progress_callback: 進捗通知コールバック
            separated_mode: 分離モード使用フラグ
            task_type: タスクタイプ（full, transcribe_only）
            
        Returns:
            ServiceResult: 文字起こし結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            self._validate_model_size(model_size, use_api)
            
            # APIキーの検証
            if use_api and not api_key:
                return self.create_error_result(
                    "APIキーが設定されていません",
                    "ValidationError"
                )
            
            # キャッシュチェック
            if use_cache:
                cache_key = self._generate_cache_key(
                    video_file, model_size, use_api, language
                )
                cached_result = self._load_cache(cache_key)
                if cached_result:
                    self.logger.info(f"キャッシュから読み込み: {cache_key}")
                    return self.create_success_result(
                        data=cached_result,
                        metadata={
                            'from_cache': True,
                            'cache_key': cache_key
                        }
                    )
            
            # Transcriberの選択と設定
            transcriber = self._create_transcriber(
                use_api, api_key, separated_mode
            )
            
            # 進捗通知のラップ
            wrapped_callback = self._wrap_progress_callback(progress_callback)
            
            # 文字起こし実行
            self.logger.info(f"文字起こし開始: {video_file.name}, モデル: {model_size}")
            
            result = transcriber.transcribe(
                video_path=str(video_file),
                model_size=model_size,
                language=language,
                progress_callback=wrapped_callback,
                use_cache=False,  # 内部キャッシュは使わない
                save_cache=False,
                skip_alignment=(task_type == "transcribe_only")
            )
            
            # 結果の検証
            if not result or not hasattr(result, 'segments'):
                raise ProcessingError("文字起こし結果が無効です")
            
            # キャッシュ保存
            if save_cache and use_cache:
                self._save_cache(cache_key, result)
            
            # メタデータの作成
            metadata = {
                'from_cache': False,
                'model_size': model_size,
                'use_api': use_api,
                'language': language,
                'segments_count': len(result.segments) if result.segments else 0,
                'processing_time': getattr(result, 'processing_time', None),
                'task_type': task_type
            }
            
            return self.create_success_result(
                data=result,
                metadata=metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"文字起こしエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"文字起こし処理中にエラーが発生しました: {str(e)}")
            )
    
    def get_available_caches(self, video_path: str) -> List[Dict[str, any]]:
        """利用可能なキャッシュのリストを取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            キャッシュ情報のリスト
        """
        try:
            video_file = Path(video_path)
            if not video_file.exists():
                return []
            
            # キャッシュディレクトリから関連ファイルを検索
            video_hash = self._get_file_hash(video_file)
            cache_files = list(self.cache_dir.glob(f"*_{video_hash}_*.json"))
            
            available_caches = []
            for cache_file in cache_files:
                try:
                    # キャッシュファイルから情報を抽出
                    parts = cache_file.stem.split('_')
                    if len(parts) >= 4:
                        model_size = parts[0]
                        is_api = parts[2] == 'api'
                        language = parts[3] if len(parts) > 3 else 'ja'
                        
                        # キャッシュの詳細情報を読み込み
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                        cache_info = {
                            'file_path': str(cache_file),
                            'model_size': model_size,
                            'is_api': is_api,
                            'language': language,
                            'segments_count': len(data.get('segments', [])),
                            'created_at': cache_file.stat().st_mtime
                        }
                        
                        available_caches.append(cache_info)
                        
                except Exception as e:
                    self.logger.warning(f"キャッシュファイル読み込みエラー: {cache_file}, {e}")
                    continue
            
            # 作成日時でソート（新しい順）
            available_caches.sort(key=lambda x: x['created_at'], reverse=True)
            
            return available_caches
            
        except Exception as e:
            self.logger.error(f"キャッシュリスト取得エラー: {e}")
            return []
    
    def load_from_cache(self, cache_path: str) -> Optional[TranscriptionResult]:
        """指定されたキャッシュファイルから結果を読み込み
        
        Args:
            cache_path: キャッシュファイルパス
            
        Returns:
            文字起こし結果（キャッシュがない場合はNone）
        """
        try:
            cache_file = Path(cache_path)
            if not cache_file.exists():
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # TranscriptionResultオブジェクトに復元
            return TranscriptionResult.from_dict(data)
            
        except Exception as e:
            self.logger.error(f"キャッシュ読み込みエラー: {e}")
            return None
    
    def _validate_model_size(self, model_size: str, use_api: bool):
        """モデルサイズの検証
        
        Args:
            model_size: モデルサイズ
            use_api: API使用フラグ
            
        Raises:
            ValidationError: 無効なモデルサイズの場合
        """
        if use_api:
            valid_models = ["whisper-1"]
        else:
            valid_models = ["base", "small", "medium", "large-v3"]
        
        if model_size not in valid_models:
            raise ValidationError(
                f"無効なモデルサイズ: {model_size}. "
                f"有効な値: {', '.join(valid_models)}"
            )
    
    def _create_transcriber(
        self, 
        use_api: bool, 
        api_key: Optional[str],
        separated_mode: bool
    ) -> Transcriber:
        """適切なTranscriberインスタンスを作成
        
        Args:
            use_api: API使用フラグ
            api_key: APIキー
            separated_mode: 分離モード使用フラグ
            
        Returns:
            Transcriberインスタンス
        """
        # 設定を更新
        if use_api:
            self.config.transcription.use_api = True
            self.config.transcription.api_key = api_key
        else:
            self.config.transcription.use_api = False
        
        # Transcriberの選択
        if separated_mode and not use_api:
            # 分離モードはSubprocessTranscriberを使用
            return SubprocessTranscriber(self.config)
        else:
            # 通常モードまたはAPIモード
            return SmartSplitTranscriber(self.config)
    
    def _generate_cache_key(
        self, 
        video_file: Path, 
        model_size: str, 
        use_api: bool,
        language: str
    ) -> str:
        """キャッシュキーを生成
        
        Args:
            video_file: 動画ファイル
            model_size: モデルサイズ
            use_api: API使用フラグ
            language: 言語コード
            
        Returns:
            キャッシュキー
        """
        file_hash = self._get_file_hash(video_file)
        api_str = "api" if use_api else "local"
        return f"{model_size}_{file_hash}_{api_str}_{language}"
    
    def _get_file_hash(self, file_path: Path) -> str:
        """ファイルのハッシュ値を取得
        
        Args:
            file_path: ファイルパス
            
        Returns:
            ハッシュ値（最初の8文字）
        """
        # ファイルサイズとパスからハッシュを生成（高速化のため内容は読まない）
        hash_input = f"{file_path.name}_{file_path.stat().st_size}_{file_path.stat().st_mtime}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:8]
    
    def _load_cache(self, cache_key: str) -> Optional[TranscriptionResult]:
        """キャッシュを読み込み
        
        Args:
            cache_key: キャッシュキー
            
        Returns:
            文字起こし結果（キャッシュがない場合はNone）
        """
        cache_file = self.cache_dir / f"{cache_key}.json"
        return self.load_from_cache(str(cache_file))
    
    def _save_cache(self, cache_key: str, result: TranscriptionResult):
        """キャッシュを保存
        
        Args:
            cache_key: キャッシュキー
            result: 文字起こし結果
        """
        try:
            cache_file = self.cache_dir / f"{cache_key}.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            self.logger.info(f"キャッシュ保存: {cache_key}")
        except Exception as e:
            self.logger.warning(f"キャッシュ保存エラー: {e}")
    
    def _wrap_progress_callback(
        self, 
        callback: Optional[Callable[[float, str], None]]
    ) -> Optional[Callable[[float, str], None]]:
        """進捗通知コールバックをラップ
        
        Args:
            callback: 元のコールバック
            
        Returns:
            ラップされたコールバック
        """
        if not callback:
            return None
        
        def wrapped(progress: float, message: str):
            # ログ出力
            self.logger.debug(f"進捗: {progress:.1%} - {message}")
            # 元のコールバックを呼び出し
            callback(progress, message)
        
        return wrapped