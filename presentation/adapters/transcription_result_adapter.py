"""
TranscriptionResultのアダプター

ドメインエンティティとレガシー形式の相互変換を提供します。
"""

import logging
from typing import Any

from domain.entities.transcription import TranscriptionResult, Word

logger = logging.getLogger(__name__)


class TranscriptionResultAdapter:
    """
    TranscriptionResultのアダプター

    ドメインエンティティをレガシー形式に適応させ、
    既存のコードとの互換性を提供します。
    """

    def __init__(self, domain_result: TranscriptionResult | None = None):
        """
        初期化

        Args:
            domain_result: ドメインエンティティのTranscriptionResult
        """
        self._domain_result = domain_result
        self._legacy_cache: dict[str, Any] | None = None

    @property
    def domain_result(self) -> TranscriptionResult | None:
        """ドメインエンティティを取得"""
        return self._domain_result

    def set_domain_result(self, result: TranscriptionResult) -> None:
        """ドメインエンティティを設定"""
        self._domain_result = result
        self._legacy_cache = None  # キャッシュをクリア

    def to_legacy_format(self) -> dict[str, Any]:
        """
        ドメインエンティティをレガシー形式に変換

        Returns:
            レガシー形式の辞書
        """
        if not self._domain_result:
            return {}

        # キャッシュがあれば返す
        if self._legacy_cache is not None:
            return self._legacy_cache

        try:
            # ドメインエンティティ自体がto_legacy_formatメソッドを持っている
            self._legacy_cache = self._domain_result.to_legacy_format()

            # 追加のレガシーフィールド
            self._legacy_cache["text"] = self._domain_result.text
            self._legacy_cache["words"] = self._extract_all_words_legacy()
            self._legacy_cache["chars"] = self._extract_all_chars_legacy()

            return self._legacy_cache

        except Exception as e:
            logger.error(f"レガシー形式への変換エラー: {e}", exc_info=True)
            return {}

    def _convert_words_to_legacy(self, words: list[Word]) -> list[dict[str, Any]]:
        """Wordリストをレガシー形式に変換"""
        return [word.to_dict() for word in words]

    def _extract_all_words_legacy(self) -> list[dict[str, Any]]:
        """すべての単語情報をレガシー形式で抽出"""
        all_words = []
        for segment in self._domain_result.segments:
            if segment.words:
                all_words.extend([word.to_dict() for word in segment.words])
        return all_words

    def _extract_all_chars_legacy(self) -> list[dict[str, Any]]:
        """すべての文字情報をレガシー形式で抽出"""
        all_chars = []
        for segment in self._domain_result.segments:
            if segment.chars:
                all_chars.extend([char.to_dict() for char in segment.chars])
        return all_chars

    @classmethod
    def from_legacy_format(cls, legacy_data: Any) -> "TranscriptionResultAdapter":
        """
        レガシー形式からドメインエンティティに変換

        Args:
            legacy_data: レガシー形式の辞書またはオブジェクト

        Returns:
            TranscriptionResultAdapter
        """
        try:
            # レガシーオブジェクトの場合は辞書に変換
            if hasattr(legacy_data, "__dict__") and not isinstance(legacy_data, dict):
                # TranscriptionResultオブジェクトから辞書形式に変換
                legacy_dict = {
                    "language": legacy_data.language,
                    "segments": [
                        {
                            "start": seg.start,
                            "end": seg.end,
                            "text": seg.text,
                            "words": seg.words if hasattr(seg, "words") else None,
                            "chars": seg.chars if hasattr(seg, "chars") else None,
                        }
                        for seg in legacy_data.segments
                    ],
                    "original_audio_path": str(legacy_data.original_audio_path),
                    "model_size": legacy_data.model_size,
                    "processing_time": getattr(legacy_data, "processing_time", 0.0),
                }
            else:
                legacy_dict = legacy_data

            # ドメインエンティティのfrom_legacy_formatメソッドを使用
            domain_result = TranscriptionResult.from_legacy_format(legacy_dict)

            # アダプターを作成して返す
            adapter = cls(domain_result)
            adapter._legacy_cache = legacy_dict  # 元のレガシーデータをキャッシュ
            return adapter

        except Exception as e:
            logger.error(f"レガシー形式からの変換エラー: {e}", exc_info=True)
            return cls()  # 空のアダプターを返す

    # レガシー互換メソッド
    def get_full_text(self) -> str:
        """レガシーのget_full_textメソッドを提供"""
        if self._domain_result:
            return self._domain_result.text
        return ""

    @property
    def segments(self) -> list[dict[str, Any]]:
        """レガシー形式のセグメントを提供"""
        if self._legacy_cache:
            return self._legacy_cache.get("segments", [])
        legacy_format = self.to_legacy_format()
        return legacy_format.get("segments", [])

    @property
    def words(self) -> list[dict[str, Any]]:
        """レガシー形式の単語リストを提供"""
        if self._legacy_cache:
            return self._legacy_cache.get("words", [])
        legacy_format = self.to_legacy_format()
        return legacy_format.get("words", [])

    @property
    def chars(self) -> list[dict[str, Any]]:
        """レガシー形式の文字リストを提供"""
        if self._legacy_cache:
            return self._legacy_cache.get("chars", [])
        legacy_format = self.to_legacy_format()
        return legacy_format.get("chars", [])

    @property
    def text(self) -> str:
        """レガシー形式のtextプロパティを提供"""
        return self.get_full_text()

    @property
    def language(self) -> str:
        """言語コードを取得"""
        if self._domain_result:
            return self._domain_result.language
        return "ja"

    def __bool__(self) -> bool:
        """真偽値評価"""
        return self._domain_result is not None

    def __repr__(self) -> str:
        """文字列表現"""
        if self._domain_result:
            return f"<TranscriptionResultAdapter segments={len(self._domain_result.segments)}>"
        return "<TranscriptionResultAdapter empty>"
