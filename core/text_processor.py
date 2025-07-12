"""
テキスト処理モジュール（差分検出、位置特定など）
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from utils.logging import get_logger

from .transcription import TranscriptionResult, TranscriptionSegment

logger = get_logger(__name__)


@dataclass
class TextPosition:
    """テキスト内の位置情報"""

    start: int
    end: int
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class ContextPattern:
    """文脈指定パターン"""

    target_text: str  # 検索対象のテキスト
    before_context: str | None = None  # 前文脈
    after_context: str | None = None  # 後文脈

    def has_context(self) -> bool:
        """文脈指定があるかどうか"""
        return self.before_context is not None or self.after_context is not None


@dataclass
class TextDifference:
    """テキストの差分情報"""

    original_text: str
    edited_text: str
    common_positions: list[TextPosition]
    added_chars: set[str]
    added_positions: list[TextPosition] = None  # 追加文字の位置情報

    def has_additions(self) -> bool:
        """追加された文字があるか"""
        return len(self.added_chars) > 0

    def get_time_ranges(self, transcription: TranscriptionResult) -> list[tuple[float, float]]:
        """共通部分のタイムスタンプを取得"""
        time_ranges = []
        not_found_positions = []

        for pos in self.common_positions:
            start_time, end_time = self._get_timestamp_for_position(transcription.segments, pos.start, pos.end)
            if start_time is not None and end_time is not None:
                time_ranges.append((start_time, end_time))
            else:
                # 見つからなかった位置の詳細を記録
                not_found_info = {
                    "text": pos.text[:50] + ("..." if len(pos.text) > 50 else ""),
                    "position": f"{pos.start}-{pos.end}",
                    "start_found": start_time is not None,
                    "end_found": end_time is not None,
                }
                not_found_positions.append(not_found_info)
                logger.warning(
                    f"タイムスタンプが見つかりません: '{not_found_info['text']}' "
                    f"(位置: {not_found_info['position']}, "
                    f"開始: {'✓' if not_found_info['start_found'] else '✗'}, "
                    f"終了: {'✓' if not_found_info['end_found'] else '✗'})"
                )

        # 見つからなかった位置が多い場合は詳細なエラーを表示
        if len(not_found_positions) > 0:
            total_positions = len(self.common_positions)
            not_found_count = len(not_found_positions)
            not_found_ratio = not_found_count / total_positions if total_positions > 0 else 0

            if not_found_ratio > 0.1:  # 10%以上が見つからない場合
                from utils.exceptions import VideoProcessingError

                error_msg = (
                    f"多くのテキスト位置でタイムスタンプが見つかりません。\n"
                    f"見つからなかった箇所: {not_found_count}/{total_positions} ({not_found_ratio:.1%})\n\n"
                )

                # 最初の3つの例を表示
                for i, info in enumerate(not_found_positions[:3]):
                    error_msg += f"例{i + 1}: {info['text']} (位置: {info['position']})\n"

                if not_found_count > 3:
                    error_msg += f"...他{not_found_count - 3}件\n"

                error_msg += "\n文字起こしを再実行するか、テキストの編集内容を確認してください。"

                raise VideoProcessingError(error_msg)
            elif not_found_count > 0:
                logger.info(
                    f"一部のテキスト位置でタイムスタンプが見つかりませんでした "
                    f"({not_found_count}/{total_positions})。処理を続行します。"
                )

        return time_ranges

    def get_time_ranges_with_words(self, transcription: TranscriptionResult) -> list[tuple[float, float, list]]:
        """共通部分のタイムスタンプと単語情報を取得"""
        time_ranges_with_words = []
        not_found_positions = []

        for pos in self.common_positions:
            start_time, end_time, words = self._get_timestamp_and_words_for_position(
                transcription.segments, pos.start, pos.end
            )
            if start_time is not None and end_time is not None:
                time_ranges_with_words.append((start_time, end_time, words))
            else:
                # 見つからなかった位置の詳細を記録
                not_found_info = {
                    "text": pos.text[:50] + ("..." if len(pos.text) > 50 else ""),
                    "position": f"{pos.start}-{pos.end}",
                }
                not_found_positions.append(not_found_info)

        # エラーハンドリング
        if time_ranges_with_words:
            total_positions = len(self.common_positions)
            not_found_count = len(not_found_positions)

            if not_found_count == total_positions:
                # 全て見つからなかった場合
                logger.error(f"タイムスタンプが全く見つかりませんでした。見つからなかった位置: {not_found_positions}")
                from utils.exceptions import VideoProcessingError

                error_msg = (
                    "テキストの位置からタイムスタンプを特定できませんでした。\n"
                    "以下の原因が考えられます：\n"
                    "1. 編集したテキストが元の文字起こしと大きく異なる\n"
                    "2. 文字起こし結果に詳細な位置情報が含まれていない\n"
                    "3. テキストの前後に余分な空白や改行が含まれている"
                )

                raise VideoProcessingError(error_msg)
            elif not_found_count > 0:
                logger.info(
                    f"一部のテキスト位置でタイムスタンプが見つかりませんでした "
                    f"({not_found_count}/{total_positions})。処理を続行します。"
                )

        return time_ranges_with_words

    def _get_timestamp_for_position(
        self, segments: list[TranscriptionSegment], start_pos: int, end_pos: int
    ) -> tuple[float | None, float | None]:
        """文字位置からタイムスタンプを取得"""
        # デバッグ情報の収集
        target_text = ""
        if hasattr(self, "original_text"):
            target_text = self.original_text[start_pos : min(end_pos, start_pos + 50)]

        debug_info = {
            "target_position": f"{start_pos}-{end_pos}",
            "target_text": target_text,
            "segments_checked": 0,
            "words_checked": 0,
            "words_without_timestamp": 0,
        }

        try:
            start_time = None
            end_time = None
            current_pos = 0

            # タイムスタンプが欠落した場合の推定用

            for seg_idx, seg in enumerate(segments):
                debug_info["segments_checked"] += 1

                # wordsが必須 - ない場合はエラー
                if not seg.words or len(seg.words) == 0:
                    from utils.exceptions import VideoProcessingError

                    raise VideoProcessingError(
                        f"検索に必要な詳細な文字位置情報がありません。"
                        f"文字起こしを再実行してください。"
                        f"\n(セグメント{seg_idx}: {seg.text[:30]}...)"
                    )

                for word_idx, word in enumerate(seg.words):
                    debug_info["words_checked"] += 1

                    try:
                        # WordInfoオブジェクトか辞書かを判定
                        if hasattr(word, "word"):
                            # WordInfoオブジェクトの場合
                            word_text = word.word
                            word_start = word.start
                            word_end = word.end
                        else:
                            # 辞書の場合
                            word_text = word.get("word", "")
                            word_start = word.get("start")
                            word_end = word.get("end")

                        word_len = len(word_text)

                        # タイムスタンプが欠落している場合
                        if word_start is None or word_end is None:
                            debug_info["words_without_timestamp"] += 1
                            logger.warning(f"タイムスタンプが欠落しているword: {word_text}")

                            # より精密な推定処理
                            # 前後の有効なタイムスタンプを収集（より広い範囲）
                            prev_timestamps = []
                            next_timestamps = []

                            # 前方検索（最大5つ前まで）
                            for prev_idx in range(max(0, word_idx - 5), word_idx):
                                prev_word = seg.words[prev_idx]
                                if hasattr(prev_word, "start") and hasattr(prev_word, "end"):
                                    if prev_word.start is not None and prev_word.end is not None:
                                        prev_timestamps.append((prev_idx, prev_word.start, prev_word.end))
                                elif (
                                    isinstance(prev_word, dict)
                                    and prev_word.get("start") is not None
                                    and prev_word.get("end") is not None
                                ):
                                    prev_timestamps.append((prev_idx, prev_word["start"], prev_word["end"]))

                            # 後方検索（最大5つ後まで）
                            for next_idx in range(word_idx + 1, min(len(seg.words), word_idx + 6)):
                                next_word = seg.words[next_idx]
                                if hasattr(next_word, "start") and hasattr(next_word, "end"):
                                    if next_word.start is not None and next_word.end is not None:
                                        next_timestamps.append((next_idx, next_word.start, next_word.end))
                                elif (
                                    isinstance(next_word, dict)
                                    and next_word.get("start") is not None
                                    and next_word.get("end") is not None
                                ):
                                    next_timestamps.append((next_idx, next_word["start"], next_word["end"]))

                            # 線形補間による推定
                            estimated_start = None
                            estimated_end = None

                            if prev_timestamps and next_timestamps:
                                # 最も近い前後のタイムスタンプを使用
                                prev_idx, prev_start, prev_end = prev_timestamps[-1]
                                next_idx, next_start, next_end = next_timestamps[0]

                                # インデックスの差による重み付け補間
                                total_gap = next_idx - prev_idx
                                current_gap = word_idx - prev_idx
                                ratio = current_gap / total_gap if total_gap > 0 else 0.5

                                # 開始時間の推定
                                estimated_start = prev_end + (next_start - prev_end) * ratio

                                # 終了時間の推定（平均的な発話速度を考慮）
                                avg_duration = (prev_end - prev_start + next_end - next_start) / 2
                                estimated_end = estimated_start + avg_duration * 0.8  # 少し短めに見積もる

                                logger.info(
                                    f"タイムスタンプを線形補間で推定: {word_text} "
                                    f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)"
                                )

                            elif prev_timestamps:
                                # 前のタイムスタンプのみある場合
                                prev_idx, prev_start, prev_end = prev_timestamps[-1]
                                avg_duration = prev_end - prev_start
                                estimated_start = prev_end + 0.1  # 小さなギャップを仮定
                                estimated_end = estimated_start + avg_duration

                                logger.info(
                                    f"タイムスタンプを前方から推定: {word_text} "
                                    f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)"
                                )

                            elif next_timestamps:
                                # 後のタイムスタンプのみある場合
                                next_idx, next_start, next_end = next_timestamps[0]
                                avg_duration = next_end - next_start
                                estimated_end = next_start - 0.1  # 小さなギャップを仮定
                                estimated_start = estimated_end - avg_duration

                                logger.info(
                                    f"タイムスタンプを後方から推定: {word_text} "
                                    f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)"
                                )

                            else:
                                # セグメントのタイムスタンプを使用（最終手段）
                                segment_duration = seg.end - seg.start
                                word_ratio = word_idx / len(seg.words)
                                estimated_start = seg.start + segment_duration * word_ratio
                                estimated_end = estimated_start + segment_duration / len(seg.words)

                                logger.warning(
                                    f"タイムスタンプをセグメントから推定: {word_text} "
                                    f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)"
                                )

                            # 推定値を使用して処理を続行
                            if start_time is None and current_pos <= start_pos < current_pos + word_len:
                                start_time = estimated_start
                            if end_time is None and current_pos < end_pos <= current_pos + word_len:
                                end_time = estimated_end

                            current_pos += word_len
                            continue

                        # 通常の処理（タイムスタンプあり）
                        if start_time is None and current_pos <= start_pos < current_pos + word_len:
                            start_time = word_start
                        if end_time is None and current_pos < end_pos <= current_pos + word_len:
                            end_time = word_end
                        current_pos += word_len

                    except (KeyError, TypeError) as e:
                        # 不正なword形式の場合はエラー
                        from utils.exceptions import VideoProcessingError

                        raise VideoProcessingError(
                            "文字位置情報の形式が不正です。文字起こしを再実行してください。"
                        ) from e

                if start_time is not None and end_time is not None:
                    break

            return start_time, end_time

        except Exception as e:
            from utils.exceptions import VideoProcessingError

            # デバッグ情報をログに出力
            logger.error(f"タイムスタンプ取得エラー - デバッグ情報: {debug_info}")

            if isinstance(e, VideoProcessingError):
                raise
            raise VideoProcessingError(
                f"タイムスタンプ取得エラー: {str(e)}\n"
                f"対象テキスト: '{debug_info['target_text']}'\n"
                f"確認したセグメント数: {debug_info['segments_checked']}\n"
                f"確認したword数: {debug_info['words_checked']}\n"
                f"タイムスタンプ欠落word数: {debug_info['words_without_timestamp']}"
            ) from e

    def _get_timestamp_and_words_for_position(
        self, segments: list[TranscriptionSegment], start_pos: int, end_pos: int
    ) -> tuple[float | None, float | None, list]:
        """文字位置からタイムスタンプと単語情報を取得"""
        start_time = None
        end_time = None
        words_in_range = []
        current_pos = 0

        for seg in segments:
            if not seg.words:
                continue

            for word in seg.words:
                # WordInfoオブジェクトか辞書かを判定
                if hasattr(word, "word"):
                    # WordInfoオブジェクトの場合
                    word_text = word.word
                    word_start = word.start
                    word_end = word.end
                else:
                    # 辞書の場合
                    word_text = word.get("word", "")
                    word_start = word.get("start")
                    word_end = word.get("end")

                word_len = len(word_text)

                # この単語が指定範囲に含まれるかチェック
                word_end_pos = current_pos + word_len

                # 単語が範囲内に含まれる場合
                if current_pos < end_pos and word_end_pos > start_pos:
                    words_in_range.append(word)

                    # 開始時刻の設定
                    if start_time is None and current_pos <= start_pos < word_end_pos:
                        start_time = word_start

                    # 終了時刻の更新
                    if current_pos < end_pos <= word_end_pos:
                        end_time = word_end
                    elif word_end_pos <= end_pos:
                        # 単語全体が範囲内の場合
                        end_time = word_end

                current_pos += word_len

                # 範囲を超えたら終了
                if current_pos >= end_pos and start_time is not None and end_time is not None:
                    break

            if start_time is not None and end_time is not None and current_pos >= end_pos:
                break

        return start_time, end_time, words_in_range


class TextProcessor:
    """テキスト処理クラス"""

    DEFAULT_SEPARATOR = "---"

    @staticmethod
    def normalize_text(text: str, preserve_newlines: bool = False) -> str:
        """テキストを正規化（空白の統一など）

        Args:
            text: 正規化するテキスト
            preserve_newlines: 改行を保持するかどうか
        """
        # 全角スペースを半角に変換
        text = text.replace("　", " ")

        if preserve_newlines:
            # 改行を一時的にマーカーに置換
            text = text.replace("\r\n", "\n")  # Windows改行を統一
            text = text.replace("\r", "\n")  # Mac改行を統一
            lines = text.split("\n")

            # 各行内の連続する空白を1つに
            normalized_lines = []
            for line in lines:
                line = re.sub(r"[ \t]+", " ", line.strip())
                normalized_lines.append(line)

            # 空行を除去して結合
            text = "\n".join(line for line in normalized_lines if line)
        else:
            # 連続する空白（改行含む）を1つのスペースに
            text = re.sub(r"\s+", " ", text)

        # 前後の空白を削除
        return text.strip()

    @staticmethod
    def remove_spaces(text: str) -> str:
        """テキストから空白を除去"""
        return re.sub(r"\s+", "", text)

    @staticmethod
    def normalize_for_matching(text: str, language: str = "ja") -> str:
        """マッチング用のテキスト正規化（言語対応）

        Args:
            text: 正規化するテキスト
            language: 言語コード（'ja', 'en'など）
        """
        # 全角スペースを半角に変換
        text = text.replace("　", " ")

        if language == "ja":
            # 日本語の場合：単語間のスペースは基本的に削除
            # ただし、英数字の前後のスペースは保持

            # 英数字と日本語文字の境界にマーカーを挿入
            text = re.sub(r"([a-zA-Z0-9]+)([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])", r"\1 \2", text)
            text = re.sub(r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF])([a-zA-Z0-9]+)", r"\1 \2", text)

            # 連続するスペースを1つに
            text = re.sub(r"\s+", " ", text)

            # 記号の前後のスペースを削除（句読点など）
            text = re.sub(r"\s*([。、！？])\s*", r"\1", text)

        else:
            # 英語の場合：連続するスペースのみ正規化
            text = re.sub(r"\s+", " ", text)

        return text.strip()

    def parse_context_pattern(self, text: str) -> ContextPattern:
        """
        文脈指定パターンを解析

        Args:
            text: 解析するテキスト (例: "{前文脈}ターゲット{後文脈}")

        Returns:
            ContextPattern: 文脈パターン情報
        """
        # 空文字列チェック
        if not text or not text.strip():
            return ContextPattern(target_text=text)

        text = text.strip()

        # パターン: {前文脈}ターゲット{後文脈}
        # 正規表現ではなく、シンプルな文字列操作で解析
        before_context = None
        after_context = None
        target_text = text

        # 前文脈の抽出
        if text.startswith("{"):
            closing_brace = text.find("}")
            if closing_brace > 0:
                before_context = text[1:closing_brace]
                target_text = text[closing_brace + 1 :]

        # 後文脈の抽出
        if target_text and "{" in target_text:
            last_opening_brace = target_text.rfind("{")
            if last_opening_brace >= 0 and target_text.endswith("}"):
                after_context = target_text[last_opening_brace + 1 : -1]
                target_text = target_text[:last_opening_brace]

        return ContextPattern(
            target_text=target_text,
            before_context=before_context if before_context else None,
            after_context=after_context if after_context else None,
        )

    def find_with_context(self, text: str, pattern: ContextPattern) -> list[int]:
        """
        文脈を考慮してテキストを検索

        Args:
            text: 検索対象のテキスト
            pattern: 文脈パターン

        Returns:
            マッチした位置のリスト（開始位置）
        """
        if not pattern.target_text:
            return []

        candidates = []

        # ターゲットテキストの全出現位置を検索
        pos = 0
        while True:
            idx = text.find(pattern.target_text, pos)
            if idx == -1:
                break

            # 文脈チェック
            if self._check_context(text, idx, pattern):
                candidates.append(idx)

            pos = idx + 1

        return candidates

    def _check_context(self, text: str, position: int, pattern: ContextPattern) -> bool:
        """
        指定位置が文脈条件を満たすかチェック

        Args:
            text: 全体テキスト
            position: ターゲットテキストの位置
            pattern: 文脈パターン

        Returns:
            文脈条件を満たすかどうか
        """
        target_len = len(pattern.target_text)

        # 前文脈のチェック
        if pattern.before_context:
            before_len = len(pattern.before_context)
            before_start = position - before_len

            # テキストの範囲外
            if before_start < 0:
                return False

            # 前文脈が一致しない
            if text[before_start:position] != pattern.before_context:
                return False

        # 後文脈のチェック
        if pattern.after_context:
            after_start = position + target_len
            after_end = after_start + len(pattern.after_context)

            # テキストの範囲外
            if after_end > len(text):
                return False

            # 後文脈が一致しない
            if text[after_start:after_end] != pattern.after_context:
                return False

        return True

    def find_differences(self, original: str, edited: str, skip_normalization: bool = False) -> TextDifference:
        """
        元のテキストと編集後のテキストの差分を検出

        Args:
            original: 元のテキスト
            edited: 編集後のテキスト
            skip_normalization: 正規化をスキップするかどうか

        Returns:
            TextDifference: 差分情報
        """
        try:
            # 入力検証
            if not isinstance(original, str) or not isinstance(edited, str):
                from utils.exceptions import VideoProcessingError

                raise VideoProcessingError("テキスト差分検出: 入力は文字列である必要があります")

            # テキストを正規化（スキップオプション対応）
            if not skip_normalization:
                original = self.normalize_text(original)
                edited = self.normalize_text(edited)

            # 編集テキストが元のテキストより短い場合、抜粋として扱う
            if len(edited) < len(original) * 0.5:  # 元のテキストの半分未満の場合
                logger.info(f"編集テキストが短い（{len(edited)}文字 vs {len(original)}文字）ため、抜粋として処理")
                return self._find_differences_for_excerpt(original, edited, skip_normalization)

            # 空白を除去したテキストで差分を計算
            original_no_spaces = self.remove_spaces(original)
            edited_no_spaces = self.remove_spaces(edited)

            # 差分を計算
            matcher = SequenceMatcher(None, original_no_spaces, edited_no_spaces)
            common_positions = []
            added_chars = set()
            added_positions = []

        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"テキスト差分検出エラー: {str(e)}") from e

        try:
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    # 元のテキストでの位置を計算
                    original_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                    length = self._calculate_length_with_spaces(original, original_pos, i2 - i1)

                    common_positions.append(
                        TextPosition(
                            start=original_pos,
                            end=original_pos + length,
                            text=original[original_pos : original_pos + length],
                        )
                    )

                elif tag in ["insert", "replace"]:
                    # 追加された文字を収集
                    added_text = edited_no_spaces[j1:j2]
                    added_chars.update(c for c in added_text if not c.isspace())

                    # 追加文字の位置情報を記録（編集後テキストでの位置）
                    if tag == "insert":
                        # 挿入の場合：元テキストでの挿入位置を特定
                        insert_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                        added_positions.append(
                            TextPosition(
                                start=insert_pos, end=insert_pos, text=edited_no_spaces[j1:j2]  # 挿入位置なので長さは0
                            )
                        )
                    elif tag == "replace":
                        # 置換の場合：元テキストでの置換位置
                        replace_pos = self._convert_position_with_spaces(original, original_no_spaces, i1)
                        replace_length = self._calculate_length_with_spaces(original, replace_pos, i2 - i1)
                        added_positions.append(
                            TextPosition(
                                start=replace_pos, end=replace_pos + replace_length, text=edited_no_spaces[j1:j2]
                            )
                        )

            return TextDifference(
                original_text=original,
                edited_text=edited,
                common_positions=common_positions,
                added_chars=added_chars,
                added_positions=added_positions,
            )

        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"差分計算処理エラー: {str(e)}") from e

    def _convert_position_with_spaces(self, text_with_spaces: str, text_no_spaces: str, pos_no_spaces: int) -> int:
        """空白を除去したテキストの位置を、元のテキストの位置に変換"""
        original_pos = 0
        no_spaces_pos = 0

        while no_spaces_pos < pos_no_spaces and original_pos < len(text_with_spaces):
            if not text_with_spaces[original_pos].isspace():
                no_spaces_pos += 1
            original_pos += 1

        return original_pos

    def _calculate_length_with_spaces(self, text: str, start_pos: int, length_no_spaces: int) -> int:
        """空白を除去した長さから、元のテキストでの長さを計算"""
        length = 0
        no_spaces_count = 0

        while no_spaces_count < length_no_spaces and start_pos + length < len(text):
            if not text[start_pos + length].isspace():
                no_spaces_count += 1
            length += 1

        return length

    def _find_differences_for_excerpt(
        self, original: str, excerpt: str, skip_normalization: bool = False
    ) -> TextDifference:
        """
        抜粋テキストの差分を検出（元のテキストから抜粋部分を探す）

        Args:
            original: 元のテキスト（全文）
            excerpt: 抜粋テキスト
            skip_normalization: 正規化をスキップするかどうか

        Returns:
            TextDifference: 差分情報
        """
        # 抜粋から句読点と改行を除去したバージョンを作成
        # ユーザーが追加した句読点や改行を追跡するため
        excerpt_no_punct = (
            excerpt.replace("。", "")
            .replace("！", "")
            .replace("？", "")
            .replace(".", "")
            .replace("!", "")
            .replace("?", "")
            .replace("\n", "")
            .replace("\r", "")
        )

        # 元のテキストから抜粋部分を探す
        position = original.find(excerpt_no_punct)

        if position == -1:
            # スペースの違いがある可能性があるので、スペースも除去して再検索
            excerpt_no_space = excerpt_no_punct.replace(" ", "")
            original_no_space = original.replace(" ", "")
            position_no_space = original_no_space.find(excerpt_no_space)

            if position_no_space != -1:
                # スペースなしで見つかった場合、元のテキストでの位置を推定
                # （これは概算になるが、後の処理で正確な位置を特定する）
                char_count = 0
                for i, char in enumerate(original):
                    if char != " ":
                        if char_count == position_no_space:
                            position = i
                            break
                        char_count += 1
                logger.info(f"スペースを除去して抜粋を発見: 位置={position}")
                # スペースなしで見つかった場合は、以降の処理でスペースを考慮する必要がある
                # フラグを設定
                space_mismatch = True
            else:
                space_mismatch = False
        else:
            space_mismatch = False

        if position == -1:
            # 見つからない場合は、正規化してから再検索
            if not skip_normalization:
                normalized_original = self.normalize_text(original)
                normalized_search = self.normalize_text(excerpt_no_punct)
                position = normalized_original.find(normalized_search)

                if position != -1:
                    # 正規化前の位置に変換（概算）
                    position = self._estimate_original_position(original, normalized_original, position)

        if position == -1:
            # それでも見つからない場合は、全体を追加文字として扱う
            logger.warning(f"抜粋テキストが元のテキストに見つかりません（抜粋: {len(excerpt)}文字）")
            return TextDifference(
                original_text=original,
                edited_text=excerpt,
                common_positions=[],
                added_chars=set(c for c in excerpt if not c.isspace()),
                added_positions=[TextPosition(start=0, end=len(excerpt), text=excerpt)],
            )

        # 見つかった場合
        if space_mismatch:
            # スペースの不一致がある場合、元のテキストから実際の終了位置を計算
            char_count = 0
            end_position = position
            for i in range(position, len(original)):
                if original[i] != " ":
                    char_count += 1
                if char_count >= len(excerpt_no_space):
                    end_position = i + 1
                    break
            found_text = original[position:end_position]
        else:
            found_text = original[position : position + len(excerpt_no_punct)]

        # 抜粋と元のテキストを比較して、追加された文字（主に句読点）を検出
        added_chars = set()
        added_positions = []

        # 抜粋と元のテキストを文字ごとに比較
        # 句読点が追加された位置を追跡
        if space_mismatch:
            # スペースの不一致がある場合の特別な処理
            original_idx = 0
            excerpt_idx = 0
            common_parts = []
            current_common_start = None
            current_common_text = ""

            while excerpt_idx < len(excerpt) and original_idx < len(found_text):
                # スペースをスキップする比較
                while (
                    original_idx < len(found_text) and found_text[original_idx] == " " and excerpt[excerpt_idx] != " "
                ):
                    original_idx += 1

                if original_idx >= len(found_text):
                    break

                if excerpt[excerpt_idx] == found_text[original_idx]:
                    # 一致する文字
                    if current_common_start is None:
                        current_common_start = position + original_idx
                    current_common_text += excerpt[excerpt_idx]
                    original_idx += 1
                    excerpt_idx += 1
                elif excerpt[excerpt_idx] in "。！？.,!?\n\r":
                    # 追加された句読点または改行
                    added_chars.add(excerpt[excerpt_idx])
                    if current_common_start is not None:
                        # 現在の共通部分を保存
                        common_parts.append(
                            TextPosition(
                                start=current_common_start, end=position + original_idx, text=current_common_text
                            )
                        )
                        current_common_start = None
                        current_common_text = ""
                    # 追加位置を記録
                    added_positions.append(
                        TextPosition(
                            start=position + original_idx, end=position + original_idx, text=excerpt[excerpt_idx]
                        )
                    )
                    excerpt_idx += 1
                else:
                    # 一致しない
                    logger.warning(
                        f"スペース不一致での比較エラー: 位置{excerpt_idx}, 抜粋='{excerpt[excerpt_idx]}', 元='{found_text[original_idx]}'"
                    )
                    excerpt_idx += 1
                    original_idx += 1
        else:
            # 通常の処理
            original_idx = 0
            excerpt_idx = 0
            common_parts = []
            current_common_start = None
            current_common_text = ""

            while excerpt_idx < len(excerpt) and original_idx < len(found_text):
                if excerpt[excerpt_idx] == found_text[original_idx]:
                    # 一致する文字
                    if current_common_start is None:
                        current_common_start = position + original_idx
                    current_common_text += excerpt[excerpt_idx]
                    original_idx += 1
                    excerpt_idx += 1
                elif excerpt[excerpt_idx] in "。！？.,!?\n\r":
                    # 追加された句読点または改行
                    added_chars.add(excerpt[excerpt_idx])
                    if current_common_start is not None:
                        # 現在の共通部分を保存
                        common_parts.append(
                            TextPosition(
                                start=current_common_start, end=position + original_idx, text=current_common_text
                            )
                        )
                        current_common_start = None
                        current_common_text = ""
                    # 追加位置を記録
                    added_positions.append(
                        TextPosition(
                            start=position + original_idx, end=position + original_idx, text=excerpt[excerpt_idx]
                        )
                    )
                    excerpt_idx += 1
                else:
                    # 一致しない（あり得ないはずだが念のため）
                    logger.warning(
                        f"予期しない不一致: 位置{excerpt_idx}, 抜粋='{excerpt[excerpt_idx]}', 元='{found_text[original_idx]}'"
                    )
                    excerpt_idx += 1
                    original_idx += 1

        # 最後の共通部分を保存
        if current_common_start is not None:
            common_parts.append(
                TextPosition(start=current_common_start, end=position + original_idx, text=current_common_text)
            )

        # 抜粋の残りの部分（もしあれば）
        if excerpt_idx < len(excerpt):
            remaining = excerpt[excerpt_idx:]
            added_chars.update(c for c in remaining if not c.isspace())
            if remaining.strip():
                added_positions.append(
                    TextPosition(start=position + len(found_text), end=position + len(found_text), text=remaining)
                )

        # 共通部分がない場合は、元のテキスト全体を共通部分とする
        if not common_parts:
            common_parts = [TextPosition(start=position, end=position + len(found_text), text=found_text)]

        return TextDifference(
            original_text=original,
            edited_text=excerpt,
            common_positions=common_parts,
            added_chars=added_chars,
            added_positions=added_positions,
        )

    def _estimate_original_position(self, original: str, normalized: str, normalized_pos: int) -> int:
        """
        正規化後の位置から元のテキストでの位置を推定
        """
        if normalized_pos == 0:
            return 0

        # 簡易的な推定：文字数の比率で計算
        if len(normalized) > 0:
            ratio = len(original) / len(normalized)
            return int(normalized_pos * ratio)

        return 0

    def split_text_into_lines(self, text: str, chars_per_line: int, max_lines: int) -> list[str]:
        """
        テキストを行数と文字数制限に基づいて分割（字幕用）

        Args:
            text: 分割するテキスト
            chars_per_line: 1行あたりの最大文字数
            max_lines: 最大行数

        Returns:
            分割されたテキストのリスト
        """
        # 空文字列の場合は空リストを返す
        if not text.strip():
            return []

        # 文末で分割（簡単な方法に変更）
        # 句読点や助詞での自然な区切りを考慮
        text = text.strip()

        # まず文字数制限内に収まる場合はそのまま返す
        if len(text) <= chars_per_line * max_lines:
            # 単純に文字数で分割
            lines = []
            for i in range(0, len(text), chars_per_line):
                line = text[i : i + chars_per_line]
                if line.strip():
                    lines.append(line.strip())
            return lines

        # 長いテキストの場合は既存の方法
        sentences = re.split(r"([。．！？、])", text)
        sentences = ["".join(i) for i in zip(sentences[::2], sentences[1::2] + [""], strict=False)]
        sentences = [s for s in sentences if s.strip()]  # 空文字列を除去

        lines = []
        current_line = ""

        for sentence in sentences:
            potential_line = current_line + sentence

            if len(potential_line) <= chars_per_line:
                current_line = potential_line
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""

                # 文が1行の文字数制限を超える場合は分割
                if len(sentence) > chars_per_line:
                    words = re.findall(r"[一-龯ぁ-んァ-ンa-zA-Z0-9]+|[^一-龯ぁ-んァ-ンa-zA-Z0-9]", sentence)
                    temp_line = ""

                    for word in words:
                        if len(temp_line + word) <= chars_per_line:
                            temp_line += word
                        else:
                            if temp_line:
                                lines.append(temp_line)
                            temp_line = word if len(word) <= chars_per_line else word[:chars_per_line]

                    if temp_line:
                        current_line = temp_line
                else:
                    current_line = sentence

        # 最後の行を追加
        if current_line:
            lines.append(current_line)

        # 行数制限を適用
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1]
            last_line = " ".join(lines[max_lines - 1 :])
            if len(last_line) > chars_per_line:
                last_line = last_line[: chars_per_line - 3] + "..."
            lines.append(last_line)

        return lines

    def split_text_by_separator(self, text: str, separator: str = None) -> list[str]:
        """
        区切り文字でテキストを分割

        Args:
            text: 分割するテキスト
            separator: 区切り文字（デフォルト: ---）

        Returns:
            分割されたテキストのリスト
        """
        if separator is None:
            separator = self.DEFAULT_SEPARATOR

        # 区切り文字で分割
        sections = text.split(separator)

        # 空のセクションを除去し、前後の空白を削除
        sections = [section.strip() for section in sections if section.strip()]

        return sections

    def find_differences_with_separator(
        self, original: str, edited: str, transcription, separator: str = None, skip_normalization: bool = False
    ) -> list[tuple[float, float]]:
        """
        区切り文字と文脈指定に対応した差分検索

        Args:
            original: 元のテキスト（文字起こし結果）
            edited: 編集後のテキスト（区切り文字や文脈指定を含む可能性）
            transcription: 文字起こし結果
            separator: 区切り文字（デフォルト: ---）
            skip_normalization: 正規化をスキップするかどうか

        Returns:
            時間範囲のリスト
        """
        if separator is None:
            separator = self.DEFAULT_SEPARATOR

        # 区切り文字が含まれているかチェック
        if separator not in edited:
            # 区切り文字がない場合も文脈指定を考慮
            return self._find_differences_with_context(original, edited, transcription, skip_normalization)

        # 区切り文字で分割
        sections = self.split_text_by_separator(edited, separator)

        all_time_ranges = []

        # 各セクションについて独立して検索
        for section in sections:
            if not section.strip():
                continue

            # 各セクションで文脈指定を考慮した差分検索
            section_ranges = self._find_differences_with_context(original, section, transcription, skip_normalization)

            # 結果をマージ
            all_time_ranges.extend(section_ranges)

        # 時間範囲をソートしてマージ
        merged_ranges = self.merge_time_ranges(all_time_ranges)

        return merged_ranges

    def _find_differences_with_context(
        self, original: str, edited: str, transcription, skip_normalization: bool = False
    ) -> list[tuple[float, float]]:
        """
        文脈指定を考慮した差分検索

        Args:
            original: 元のテキスト
            edited: 編集後のテキスト（文脈指定を含む可能性）
            transcription: 文字起こし結果
            skip_normalization: 正規化をスキップするかどうか

        Returns:
            時間範囲のリスト
        """
        # 文脈パターンを解析
        pattern = self.parse_context_pattern(edited)

        # 文脈指定がある場合
        if pattern.has_context():
            # 文脈を考慮して検索
            candidates = self.find_with_context(original, pattern)

            if not candidates:
                # 見つからない場合は空のリストを返す
                logger.warning(f"文脈指定されたテキストが見つかりません: {pattern.target_text}")
                return []

            # 最初の候補を使用（将来的にはより高度な選択ロジックを実装）
            position = candidates[0]
            target_len = len(pattern.target_text)

            # 位置情報を作成
            common_positions = [TextPosition(start=position, end=position + target_len, text=pattern.target_text)]

            # TextDifferenceを作成
            diff = TextDifference(
                original_text=original,
                edited_text=pattern.target_text,
                common_positions=common_positions,
                added_chars=set(),
            )

            return diff.get_time_ranges(transcription)

        # 文脈指定がない場合は通常の処理
        diff = self.find_differences(original, edited, skip_normalization=skip_normalization)
        return diff.get_time_ranges(transcription)

    def merge_time_ranges(
        self, time_ranges: list[tuple[float, float]], gap_threshold: float = 1.0
    ) -> list[tuple[float, float]]:
        """
        時間範囲をマージ（近い範囲を結合）

        Args:
            time_ranges: 時間範囲のリスト
            gap_threshold: マージする閾値（秒）

        Returns:
            マージされた時間範囲のリスト
        """
        if not time_ranges:
            return []

        # 開始時間でソート
        sorted_ranges = sorted(time_ranges)
        merged = [sorted_ranges[0]]

        for current_start, current_end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]

            # 重複または近い範囲はマージ
            if current_start <= last_end + gap_threshold:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))

        return merged

    def parse_boundary_markers(self, text: str) -> list[dict]:
        """
        テキストから境界調整マーカーを解析

        マーカー記法:
        [数値<] = 前のクリップを左に移動（縮める）
        [数値>] = 前のクリップを右に移動（延ばす）
        [<数値] = 後のクリップを左に移動（早める）
        [>数値] = 後のクリップを右に移動（遅らせる）

        Args:
            text: 解析するテキスト

        Returns:
            境界調整情報のリスト
        """
        # マーカーパターン（負の数値にも対応）
        marker_pattern = re.compile(r"\[(-?\d+(?:\.\d+)?)[<>]\]|\[[<>](-?\d+(?:\.\d+)?)\]")

        adjustments = []

        for match in marker_pattern.finditer(text):
            marker = match.group(0)
            position = match.start()

            adjustment_info = {"position": position, "marker": marker, "target": None, "adjustment": 0.0}

            # パターンマッチング
            if marker.startswith("[") and marker.endswith(">]"):
                # [数値>] パターン：前のクリップを延ばす
                value = float(marker[1:-2])
                adjustment_info["target"] = "previous"
                adjustment_info["adjustment"] = value

            elif marker.startswith("[") and marker.endswith("<]"):
                # [数値<] パターン：前のクリップを縮める
                value = float(marker[1:-2])
                adjustment_info["target"] = "previous"
                adjustment_info["adjustment"] = -value

            elif marker.startswith("[<"):
                # [<数値] パターン：後のクリップを早める
                value = float(marker[2:-1])
                adjustment_info["target"] = "next"
                adjustment_info["adjustment"] = -value

            elif marker.startswith("[>"):
                # [>数値] パターン：後のクリップを遅らせる
                value = float(marker[2:-1])
                adjustment_info["target"] = "next"
                adjustment_info["adjustment"] = value

            if adjustment_info["target"]:
                adjustments.append(adjustment_info)

        return adjustments

    def extract_existing_markers(self, text: str) -> dict[str, dict[str, float]]:
        """
        テキストから既存マーカー情報を抽出

        Args:
            text: マーカーを含むテキスト

        Returns:
            {セグメントテキスト: {'start': 開始値, 'end': 終了値}}
        """
        markers = {}
        lines = text.split("\n")

        for line in lines:
            # 例: [<0.5]ハイパー企業ラジオっていう[1.0>]
            start_match = re.search(r"\[<(-?\d+(?:\.\d+)?)\]", line)
            end_match = re.search(r"\[(-?\d+(?:\.\d+)?)>\]", line)

            if start_match and end_match:
                # マーカーを除去したテキストを取得
                segment_text = re.sub(r"\[<?-?\d+(?:\.\d+)?>?\]", "", line).strip()
                if segment_text:
                    markers[segment_text] = {"start": float(start_match.group(1)), "end": float(end_match.group(1))}

        return markers

    def validate_marker_positions(self, text: str) -> list[str]:
        """
        マーカーの位置が適切かどうかを検証
        注：複数クリップの改行なし配置は自動修正されるため、エラーとして報告しない

        Args:
            text: 検証するテキスト

        Returns:
            エラーメッセージのリスト（空の場合は問題なし）
        """
        errors = []

        # マーカーパターン
        marker_pattern = re.compile(r"\[(-?\d+(?:\.\d+)?)[<>]\]|\[[<>](-?\d+(?:\.\d+)?)\]")

        # 改行で分割（クリップごとに1行を想定）
        lines = text.split("\n")

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # 各行のマーカーをすべて収集
            markers_in_line = list(marker_pattern.finditer(line))

            # 各マーカーの位置をチェック（セグメント内配置のみチェック）
            for match in markers_in_line:
                marker = match.group(0)
                position = match.start()

                # マーカーの前後のテキストを確認
                before_text = line[:position]
                after_text = line[position + len(marker) :]

                # [<数値] パターンは行の先頭にあるべき
                if marker.startswith("[<"):
                    # マーカーの前にテキストがある場合（ただし >] 以外）
                    if before_text.strip() and not before_text.rstrip().endswith(">]"):
                        errors.append(f"行{i + 1}: '{marker}'は行の先頭に配置してください")

                # [数値>] パターンは行の末尾にあるべき
                elif marker.endswith(">]"):
                    # マーカーの後にテキストがある場合（ただし [< 以外）
                    if after_text.strip() and not after_text.lstrip().startswith("[<"):
                        errors.append(f"行{i + 1}: '{marker}'は行の末尾に配置してください")

        return errors


    def auto_fix_marker_newlines(self, text: str) -> str:
        """
        マーカー配置の問題を自動修正

        Args:
            text: マーカーを含むテキスト

        Returns:
            修正されたテキスト
        """
        lines = text.split("\n")
        fixed_lines = []

        for _, line in enumerate(lines):
            # 空行はそのまま
            if not line.strip():
                fixed_lines.append(line)
                continue

            # マーカーパターン
            re.compile(r"\[(-?\d+(?:\.\d+)?)[<>]\]|\[[<>](-?\d+(?:\.\d+)?)\]")

            # 1. ]>][< パターンを改行に置換
            line = re.sub(r"(\[(?:-?\d+(?:\.\d+)?)>\])\s*(\[<(?:-?\d+(?:\.\d+)?)\])", r"\1\n\2", line)

            # 複数行に分割された場合の処理
            sub_lines = line.split("\n")
            for sub_line in sub_lines:
                # マーカーがあるかチェック
                has_start_marker = bool(re.search(r"\[<(?:-?\d+(?:\.\d+)?)\]", sub_line))
                has_end_marker = bool(re.search(r"\[(?:-?\d+(?:\.\d+)?)>\]", sub_line))

                # マーカーがないテキストにマーカーを追加
                if sub_line.strip() and not has_start_marker and not has_end_marker:
                    # マーカーがないテキストにはマーカーを追加
                    fixed_lines.append(f"[<0.0]{sub_line.strip()}[0.0>]")
                elif has_end_marker and not sub_line.rstrip().endswith(">]"):
                    # 終了マーカーの後にテキストがある場合
                    match = re.match(r"(.*\[(?:-?\d+(?:\.\d+)?)>\])(.+)$", sub_line)
                    if match:
                        marker_part = match.group(1)
                        text_part = match.group(2).strip()
                        fixed_lines.append(marker_part)
                        if text_part:
                            fixed_lines.append(f"[<0.0]{text_part}[0.0>]")
                    else:
                        fixed_lines.append(sub_line)
                elif has_start_marker and not sub_line.lstrip().startswith("[<"):
                    # 開始マーカーの前にテキストがある場合
                    match = re.match(r"(.+?)(\[<(?:-?\d+(?:\.\d+)?)\].*)$", sub_line)
                    if match:
                        text_part = match.group(1).strip()
                        marker_part = match.group(2)
                        if text_part:
                            fixed_lines.append(f"[<0.0]{text_part}[0.0>]")
                        fixed_lines.append(marker_part)
                    else:
                        fixed_lines.append(sub_line)
                else:
                    fixed_lines.append(sub_line)

        return "\n".join(fixed_lines)

