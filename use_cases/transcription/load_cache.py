"""
文字起こしキャッシュ読み込みユースケース
"""

from dataclasses import dataclass
from typing import Any

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.base import UseCase
from use_cases.exceptions import CacheNotFoundError, TranscriptionError
from use_cases.interfaces import ITranscriptionGateway


@dataclass
class LoadCacheRequest:
    """キャッシュ読み込みリクエスト"""

    video_path: FilePath
    model_size: str | None = None  # Noneの場合は最新のキャッシュを選択

    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))


@dataclass
class CacheInfo:
    """キャッシュ情報"""

    path: FilePath
    model_size: str
    language: str
    created_at: float
    file_size: int
    segment_count: int
    actual_filename: str | None = None  # 実際のファイル名（拡張子なし）
    is_api: bool = False  # APIモードかどうか
    mode: str = "ローカル"  # モード名


class LoadTranscriptionCacheUseCase(UseCase[LoadCacheRequest, TranscriptionResult]):
    """
    文字起こしキャッシュを読み込むユースケース

    指定されたモデルのキャッシュを読み込みます。
    モデルが指定されていない場合は、最新のキャッシュを選択します。
    """

    def __init__(self, transcription_gateway: ITranscriptionGateway):
        super().__init__()
        self.gateway = transcription_gateway

    def execute(self, request: LoadCacheRequest) -> TranscriptionResult:
        """キャッシュの読み込み"""
        # 利用可能なキャッシュの一覧を取得
        available_caches = self.gateway.list_available_caches(request.video_path)

        if not available_caches:
            raise CacheNotFoundError(f"No cache found for video: {request.video_path.name}")

        # キャッシュの選択
        selected_cache = self._select_cache(available_caches, request.model_size)

        if not selected_cache:
            raise CacheNotFoundError(
                f"No cache found for model '{request.model_size}' " f"and video: {request.video_path.name}"
            )

        self.logger.info(
            f"Loading cache: model={selected_cache['model_size']}, "
            f"is_api={selected_cache.get('is_api', False)}, "
            f"created_at={selected_cache.get('created_at', selected_cache.get('modified_time', 'unknown'))}"
        )

        try:
            # actual_filenameがある場合はそれを使用、なければmodel_sizeを使用
            cache_model_size = selected_cache.get("actual_filename", selected_cache["model_size"])

            # キャッシュの読み込み
            result = self.gateway.load_from_cache(video_path=request.video_path, model_size=cache_model_size)

            if not result:
                self.logger.warning(
                    f"Gateway returned None for cache: {request.video_path}, model: {selected_cache['model_size']}"
                )
                raise CacheNotFoundError("Cache file exists but could not be loaded")

            # 検証
            if not result.segments:
                raise TranscriptionError("Cached result has no segments")

            # word-level タイムスタンプ必須（SRT字幕境界ズレ防止）
            # 旧キャッシュは words 無しの場合があるため、再文字起こしを強制する
            if not all(getattr(s, "words", None) for s in result.segments):
                self.logger.warning(
                    "Cache missing word-level timestamps (outdated format). "
                    "Treating as cache-miss to force re-transcription."
                )
                raise CacheNotFoundError("Cache missing word-level timestamps; re-transcription required")

            self.logger.info(
                f"Cache loaded successfully. " f"Language: {result.language}, " f"Segments: {len(result.segments)}"
            )

            return result

        except CacheNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to load cache: {str(e)}")
            raise TranscriptionError(f"Failed to load cache: {str(e)}", cause=e)

    def _select_cache(self, available_caches: list[dict[str, Any]], model_size: str | None) -> dict[str, Any] | None:
        """キャッシュを選択"""
        if model_size:
            # 指定されたモデルのキャッシュを探す
            for cache in available_caches:
                # model_sizeまたはactual_filenameで一致するものを探す
                if cache.get("model_size") == model_size or cache.get("actual_filename") == model_size:
                    return cache
            return None
        else:
            # 最新のキャッシュを選択（作成日時でソート済みと仮定）
            return available_caches[0] if available_caches else None

    def list_available_caches(self, video_path: FilePath) -> list[CacheInfo]:
        """
        利用可能なキャッシュの情報を取得

        このメソッドは直接呼び出し可能なヘルパーメソッドです。
        """
        caches = self.gateway.list_available_caches(video_path)

        return [
            CacheInfo(
                path=FilePath(cache.get("file_path", cache["path"]) if "file_path" in cache else cache["path"]),
                model_size=cache["model_size"],
                language=cache.get("language", "unknown"),
                created_at=cache.get("created_at", cache.get("modified_time", 0)),
                file_size=cache.get("file_size", 0),
                segment_count=cache.get("segment_count", cache.get("segments_count", 0)),
                actual_filename=cache.get("actual_filename"),
                is_api=cache.get("is_api", False),
                mode=cache.get("mode", "ローカル"),
            )
            for cache in caches
        ]
