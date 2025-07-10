"""
LCSベースのテキスト差分検出ユースケース

フィラーを含む文字起こしに対して、より正確な差分検出を実現。
"""

from typing import List, Tuple, Optional
from uuid import uuid4

from domain.entities.text_difference import DifferenceType, TextDifference
from domain.entities.transcription import TranscriptionResult
from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.value_objects.lcs_match import LCSMatch, DifferenceBlock
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.use_cases.difference_grouper import DifferenceGrouper
from utils.logging import get_logger

logger = get_logger(__name__)


class TextDifferenceDetectorLCS:
    """
    LCSアルゴリズムを使用したテキスト差分検出

    フィラーが多い音声文字起こしでも正確にマッチングできる。
    文字レベルのタイムスタンプを活用して高精度な時間計算を実現。
    """

    def __init__(self):
        self.character_builder = CharacterArrayBuilder()
        self.difference_grouper = DifferenceGrouper()
        self.min_match_length = 2  # 最小マッチ長

    def detect_differences(
        self, original_text: str, edited_text: str, transcription_result: Optional[TranscriptionResult] = None
    ) -> TextDifference:
        """
        LCSを使用してテキストの差分を検出

        Args:
            original_text: 元のテキスト（文字起こし結果）
            edited_text: 編集後のテキスト（切り抜き指定）
            transcription_result: 文字起こし結果（時間情報用）

        Returns:
            差分情報
        """
        logger.info(f"LCS差分検出開始: 元{len(original_text)}文字 vs 編集{len(edited_text)}文字")

        # 文字配列を構築（transcription_resultがある場合）
        char_array = None
        if transcription_result:
            char_array, reconstructed_text = self.character_builder.build_from_transcription(transcription_result)
            # 重要: 必ず再構築テキストを使用する
            # CharacterArrayBuilderは文字単位でテキストを再構築するため、
            # その結果と一致するテキストを使わないと位置がズレる
            original_text = reconstructed_text
            logger.info(f"再構築テキストを使用: {len(reconstructed_text)}文字")

        # LCSを計算してマッチ位置を取得
        match_positions = self._compute_lcs_positions(original_text, edited_text)

        # マッチ情報を構築（文字配列がある場合）
        lcs_matches = None
        if char_array and match_positions:
            lcs_matches = self._create_lcs_matches(match_positions, char_array, edited_text)

        # 差分ブロックを構築
        if match_positions:
            # マッチがある場合
            if char_array and lcs_matches:
                # TranscriptionResultがある場合：詳細な時間情報付き
                groups = self.difference_grouper.group_lcs_matches(lcs_matches)
                difference_blocks = self.difference_grouper.create_difference_blocks(
                    groups, char_array, original_text, edited_text
                )
            else:
                # TranscriptionResultがない場合：時間情報なしで処理
                difference_blocks = self._create_difference_blocks_without_timestamps(
                    original_text, edited_text, match_positions
                )
        else:
            # マッチがない場合の処理
            difference_blocks = self._create_difference_blocks_no_match(original_text, edited_text, char_array)

        # レガシー形式の差分リストに変換
        differences = self._convert_to_legacy_differences(difference_blocks)

        # デバッグ情報
        unchanged_count = sum(1 for d in differences if d[0] == DifferenceType.UNCHANGED)
        deleted_count = sum(1 for d in differences if d[0] == DifferenceType.DELETED)
        added_count = sum(1 for d in differences if d[0] == DifferenceType.ADDED)
        logger.info(f"差分検出完了: {unchanged_count}個の一致, {deleted_count}個の削除, {added_count}個の追加")

        # 両方空の場合の特別処理
        if not original_text and not edited_text:
            return TextDifference(id=self._generate_id(), original_text="", edited_text="", differences=[])

        return TextDifference(
            id=self._generate_id(),
            original_text=original_text or "",
            edited_text=edited_text or "",
            differences=differences,
        )

    def detect_differences_with_blocks(
        self, original_text: str, edited_text: str, transcription_result: Optional[TranscriptionResult] = None
    ) -> Tuple[TextDifference, List[DifferenceBlock]]:
        """
        LCSを使用してテキストの差分を検出し、差分ブロックも返す

        Returns:
            (差分情報, 差分ブロックのリスト)
        """
        text_diff = self.detect_differences(original_text, edited_text, transcription_result)

        # 文字配列を構築
        char_array = None
        if transcription_result:
            char_array, _ = self.character_builder.build_from_transcription(transcription_result)

        # マッチ位置を再計算（内部状態を保持していないため）
        match_positions = self._compute_lcs_positions(original_text, edited_text)

        # マッチ情報を構築
        lcs_matches = None
        if char_array and match_positions:
            lcs_matches = self._create_lcs_matches(match_positions, char_array, edited_text)

        # 差分ブロックを構築
        if match_positions:
            # マッチがある場合
            if char_array and lcs_matches:
                # TranscriptionResultがある場合：詳細な時間情報付き
                groups = self.difference_grouper.group_lcs_matches(lcs_matches)
                difference_blocks = self.difference_grouper.create_difference_blocks(
                    groups, char_array, original_text, edited_text
                )
            else:
                # TranscriptionResultがない場合：時間情報なしで処理
                difference_blocks = self._create_difference_blocks_without_timestamps(
                    original_text, edited_text, match_positions
                )
        else:
            # マッチがない場合の処理
            difference_blocks = self._create_difference_blocks_no_match(original_text, edited_text, char_array)

        return text_diff, difference_blocks

    def _compute_lcs_positions(self, text1: str, text2: str) -> List[Tuple[int, int]]:
        """
        LCSアルゴリズムでマッチ位置を計算

        Returns:
            マッチした文字の位置ペアのリスト [(text1_index, text2_index), ...]
        """
        m, n = len(text1), len(text2)

        # 空文字列の場合
        if m == 0 or n == 0:
            return []

        # メモリ効率を考慮（巨大なテキストの場合は分割処理）
        if m * n > 100_000_000:  # 1億を超える場合
            logger.warning(f"テキストが大きすぎるため分割処理: {m}×{n}")
            return self._compute_lcs_positions_chunked(text1, text2)

        # DPテーブル構築
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if text1[i - 1] == text2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        # バックトラックしてマッチ位置を取得
        positions = []
        i, j = m, n
        while i > 0 and j > 0:
            if text1[i - 1] == text2[j - 1]:
                positions.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1

        return list(reversed(positions))

    def _compute_lcs_positions_chunked(self, text1: str, text2: str) -> List[Tuple[int, int]]:
        """大きなテキスト用の分割LCS処理"""
        # 簡易実装：text2を分割して処理
        chunk_size = 1000
        chunk_overlap = 100  # チャンク間の重複
        all_positions = []

        for start in range(0, len(text2), chunk_size - chunk_overlap):
            end = min(start + chunk_size, len(text2))
            chunk = text2[start:end]

            # チャンクごとにLCSを計算
            positions = self._compute_lcs_positions(text1, chunk)
            # オフセットを調整
            adjusted = [(p1, p2 + start) for p1, p2 in positions]
            all_positions.extend(adjusted)

        # 重複を除去してソート
        unique_positions = list(set(all_positions))
        return sorted(unique_positions)

    def _create_lcs_matches(
        self, match_positions: List[Tuple[int, int]], char_array: List[CharacterWithTimestamp], edited_text: str
    ) -> List[LCSMatch]:
        """マッチ位置からLCSMatch情報を作成"""
        lcs_matches = []

        for orig_idx, edit_idx in match_positions:
            if orig_idx < len(char_array):
                match = LCSMatch(
                    original_index=orig_idx,
                    edited_index=edit_idx,
                    char=edited_text[edit_idx],
                    timestamp=char_array[orig_idx],
                )
                lcs_matches.append(match)

        return lcs_matches

    def _create_difference_blocks_no_match(
        self, original_text: str, edited_text: str, char_array: Optional[List[CharacterWithTimestamp]] = None
    ) -> List[DifferenceBlock]:
        """マッチがない場合の差分ブロック作成"""
        blocks = []

        # 編集テキストがある場合は追加
        if edited_text:
            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.ADDED, text=edited_text, start_time=None, end_time=None, char_positions=[]
                )
            )

        # 元テキストがある場合は削除
        if original_text and char_array:
            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.DELETED,
                    text=original_text,
                    start_time=char_array[0].start if char_array else None,
                    end_time=char_array[-1].end if char_array else None,
                    char_positions=char_array.copy() if char_array else [],
                )
            )

        return blocks

    def _create_difference_blocks_without_timestamps(
        self, original_text: str, edited_text: str, match_positions: List[Tuple[int, int]]
    ) -> List[DifferenceBlock]:
        """タイムスタンプなしで差分ブロックを作成（TranscriptionResultがない場合）"""
        blocks = []

        # 連続したマッチをグループ化
        groups = self._group_continuous_matches(match_positions)

        # UNCHANGEDブロックの作成
        for group in groups:
            start_o, start_e = group[0]
            end_o, end_e = group[-1]

            matched_text = original_text[start_o : end_o + 1]

            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.UNCHANGED,
                    text=matched_text,
                    start_time=None,
                    end_time=None,
                    char_positions=[],
                    original_start_pos=start_o,
                    original_end_pos=end_o,
                )
            )

        # 削除ブロックの特定
        matched_indices = {pos[0] for pos in match_positions}
        current_deletion_start = None
        current_deletion_text = []

        for i in range(len(original_text)):
            if i not in matched_indices:
                if current_deletion_start is None:
                    current_deletion_start = i
                current_deletion_text.append(original_text[i])
            else:
                if current_deletion_text:
                    blocks.append(
                        DifferenceBlock(
                            type=DifferenceType.DELETED,
                            text="".join(current_deletion_text),
                            start_time=None,
                            end_time=None,
                            char_positions=[],
                            original_start_pos=current_deletion_start,
                            original_end_pos=current_deletion_start + len(current_deletion_text) - 1,
                        )
                    )
                    current_deletion_start = None
                    current_deletion_text = []

        # 最後の削除ブロック
        if current_deletion_text:
            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.DELETED,
                    text="".join(current_deletion_text),
                    start_time=None,
                    end_time=None,
                    char_positions=[],
                    original_start_pos=current_deletion_start,
                    original_end_pos=current_deletion_start + len(current_deletion_text) - 1,
                )
            )

        # 追加ブロックの特定
        matched_edited_indices = {pos[1] for pos in match_positions}
        current_addition_text = []

        for i in range(len(edited_text)):
            if i not in matched_edited_indices:
                current_addition_text.append(edited_text[i])
            else:
                if current_addition_text:
                    blocks.append(
                        DifferenceBlock(
                            type=DifferenceType.ADDED,
                            text="".join(current_addition_text),
                            start_time=None,
                            end_time=None,
                            char_positions=[],
                        )
                    )
                    current_addition_text = []

        # 最後の追加ブロック
        if current_addition_text:
            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.ADDED,
                    text="".join(current_addition_text),
                    start_time=None,
                    end_time=None,
                    char_positions=[],
                )
            )

        # 位置でソート
        blocks.sort(key=lambda b: (b.original_start_pos or float("inf"), b.original_end_pos or float("inf")))

        return blocks

    def _create_difference_blocks(
        self,
        original_text: str,
        edited_text: str,
        match_positions: List[Tuple[int, int]],
        char_array: Optional[List[CharacterWithTimestamp]] = None,
        lcs_matches: Optional[List[LCSMatch]] = None,
    ) -> List[DifferenceBlock]:
        """差分ブロックを作成"""
        blocks = []

        if not match_positions:
            # 完全に一致しない場合
            if edited_text:
                blocks.append(
                    DifferenceBlock(
                        type=DifferenceType.ADDED, text=edited_text, start_time=None, end_time=None, char_positions=[]
                    )
                )
            if original_text and char_array:
                # 元のテキスト全体が削除
                blocks.append(
                    DifferenceBlock(
                        type=DifferenceType.DELETED,
                        text=original_text,
                        start_time=char_array[0].start if char_array else None,
                        end_time=char_array[-1].end if char_array else None,
                        char_positions=char_array.copy() if char_array else [],
                    )
                )
            return blocks

        # 連続したマッチをグループ化
        groups = self._group_continuous_matches(match_positions)

        # UNCHANGEDブロックを作成
        for group in groups:
            start_o, start_e = group[0]
            end_o, end_e = group[-1]

            matched_text = original_text[start_o : end_o + 1]

            # 時間情報を付与
            start_time = None
            end_time = None
            char_positions = []

            if char_array and lcs_matches:
                # グループ内の文字位置情報を収集
                for pos in group:
                    if pos[0] < len(char_array):
                        char_positions.append(char_array[pos[0]])

                if char_positions:
                    start_time = char_positions[0].start
                    end_time = char_positions[-1].end

            blocks.append(
                DifferenceBlock(
                    type=DifferenceType.UNCHANGED,
                    text=matched_text,
                    start_time=start_time,
                    end_time=end_time,
                    char_positions=char_positions,
                    original_start_pos=start_o,
                    original_end_pos=end_o,
                )
            )

        # 削除ブロックを特定
        if char_array:
            deletion_blocks = self._identify_deletion_blocks(original_text, match_positions, char_array)
            blocks.extend(deletion_blocks)

        # 開始位置でソート
        blocks.sort(key=lambda b: b.original_start_pos or 0)

        return blocks

    def _group_continuous_matches(self, match_positions: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
        """連続したマッチをグループ化"""
        if not match_positions:
            return []

        groups = []
        current_group = [match_positions[0]]

        for i in range(1, len(match_positions)):
            prev_o, prev_e = match_positions[i - 1]
            curr_o, curr_e = match_positions[i]

            # 両方のテキストで連続している場合は同じグループ
            if curr_o == prev_o + 1 and curr_e == prev_e + 1:
                current_group.append(match_positions[i])
            else:
                # グループが最小マッチ長以上の場合のみ追加
                if len(current_group) >= self.min_match_length:
                    groups.append(current_group)
                current_group = [match_positions[i]]

        # 最後のグループも最小マッチ長以上の場合のみ追加
        if current_group and len(current_group) >= self.min_match_length:
            groups.append(current_group)

        return groups

    def _identify_deletion_blocks(
        self, original_text: str, match_positions: List[Tuple[int, int]], char_array: List[CharacterWithTimestamp]
    ) -> List[DifferenceBlock]:
        """削除された部分を特定"""
        deletion_blocks = []
        matched_indices = {pos[0] for pos in match_positions}

        current_deletion_start = None
        current_deletion_chars = []

        for i, char_info in enumerate(char_array):
            if i not in matched_indices:
                # 削除される文字
                if current_deletion_start is None:
                    current_deletion_start = i
                current_deletion_chars.append(char_info)
            else:
                # マッチした文字（削除ブロックの終了）
                if current_deletion_chars:
                    deletion_text = "".join([c.char for c in current_deletion_chars])
                    block = DifferenceBlock(
                        type=DifferenceType.DELETED,
                        text=deletion_text,
                        start_time=current_deletion_chars[0].start,
                        end_time=current_deletion_chars[-1].end,
                        char_positions=current_deletion_chars.copy(),
                        original_start_pos=current_deletion_start,
                        original_end_pos=current_deletion_start + len(current_deletion_chars) - 1,
                    )
                    deletion_blocks.append(block)
                    current_deletion_start = None
                    current_deletion_chars = []

        # 最後の削除ブロック
        if current_deletion_chars:
            deletion_text = "".join([c.char for c in current_deletion_chars])
            block = DifferenceBlock(
                type=DifferenceType.DELETED,
                text=deletion_text,
                start_time=current_deletion_chars[0].start,
                end_time=current_deletion_chars[-1].end,
                char_positions=current_deletion_chars.copy(),
                original_start_pos=current_deletion_start,
                original_end_pos=current_deletion_start + len(current_deletion_chars) - 1,
            )
            deletion_blocks.append(block)

        return deletion_blocks

    def _convert_to_legacy_differences(
        self, blocks: List[DifferenceBlock]
    ) -> List[Tuple[DifferenceType, str, Optional[Tuple[float, float]]]]:
        """差分ブロックをレガシー形式に変換"""
        differences = []

        for block in blocks:
            time_range = None
            if block.start_time is not None and block.end_time is not None:
                time_range = (block.start_time, block.end_time)

            differences.append((block.type, block.text, time_range))

        return differences

    def _generate_id(self) -> str:
        """ID生成"""
        return str(uuid4())
