"""
日本語の自然な改行処理

禁則処理ルールに基づいて、日本語テキストを自然な位置で改行する。
"""

import re

from utils.logging import get_logger

logger = get_logger(__name__)


class JapaneseLineBreakRules:
    """日本語の禁則処理ルール"""

    # 行頭禁則文字（行の先頭に来てはいけない）
    LINE_START_NG = set("、。，．・？！゛゜ヽヾゝゞ々ー）］｝」』!),.:;?]}°′″℃％‰")

    # 行末禁則文字（行の末尾に来てはいけない）
    LINE_END_NG = set("（［｛「『([{")

    # 分割禁止パターン（正規表現）
    NO_BREAK_PATTERNS = [
        re.compile(r"\d+[年月日時分秒]"),  # 10年、5月、3日など
        re.compile(r"\d+[％%]"),  # 50％、100%など
        re.compile(r"[A-Za-z]+\d+"),  # ABC123など
        re.compile(r"\d+\.\d+"),  # 12.34など
    ]

    # 一般的な助詞（分割を優先する位置）
    PARTICLES = set("はがをにでとも")

    # 形態素解析器（遅延初期化）
    _tokenizer = None

    @classmethod
    def _get_tokenizer(cls):
        """形態素解析器の取得（シングルトン）"""
        if cls._tokenizer is None:
            try:
                from janome.tokenizer import Tokenizer

                cls._tokenizer = Tokenizer()
                logger.info("janome形態素解析器を初期化しました")
            except ImportError:
                logger.warning("janomeがインストールされていません。基本的な改行処理のみ使用します。")
                cls._tokenizer = False
        return cls._tokenizer

    @classmethod
    def get_word_boundaries(cls, text: str) -> list[int]:
        """形態素解析による単語境界の取得"""
        tokenizer = cls._get_tokenizer()
        if not tokenizer:
            return []

        boundaries = []
        pos = 0
        for token in tokenizer.tokenize(text):
            pos += len(token.surface)
            boundaries.append(pos)
            logger.debug(f"単語: '{token.surface}' 境界位置: {pos}")
        return boundaries

    @classmethod
    def get_word_boundaries_with_pos(cls, text: str) -> list[tuple[int, str, str]]:
        """形態素解析による単語境界と品詞情報の取得"""
        tokenizer = cls._get_tokenizer()
        if not tokenizer:
            return []

        boundaries = []
        pos = 0
        for token in tokenizer.tokenize(text):
            pos += len(token.surface)
            # (境界位置, 表層形, 品詞)
            pos_tag = token.part_of_speech.split(",")[0]
            boundaries.append((pos, token.surface, pos_tag))
            logger.debug(f"単語: '{token.surface}' 品詞: {pos_tag} 境界位置: {pos}")
        return boundaries

    @classmethod
    def evaluate_break_position(cls, boundaries: list[tuple[int, str, str]], position: int) -> float:
        """改行位置の良さをスコア化

        Args:
            boundaries: 品詞情報付き単語境界リスト
            position: 評価する改行位置

        Returns:
            スコア（高いほど良い改行位置）
        """
        score = 1.0

        # 境界位置を見つける
        for i, (boundary, surface, pos_tag) in enumerate(boundaries):
            if boundary == position:
                logger.debug(f"位置{position}の評価: 単語'{surface}'({pos_tag})の後")

                # 名詞の直後は改行しやすい（ただし数詞の連続は避ける）
                if pos_tag == "名詞":
                    # 単位（月、日、時など）の後かどうかをチェック
                    if surface in "月日時分秒年":
                        # 前の単語が数詞なら改行を避ける
                        if i > 0:
                            prev_surface = boundaries[i - 1][1]
                            prev_pos = boundaries[i - 1][2]
                            if prev_pos == "名詞" and (
                                prev_surface.isdigit() or any(c in prev_surface for c in "0123456789")
                            ):
                                score *= 0.05  # 強く避ける
                                logger.debug(f"数詞+単位の組み合わせのため改行を避ける: {prev_surface}{surface}")
                    # 数詞かどうかをチェック
                    elif surface.isdigit() or any(c in surface for c in "0123456789"):
                        # 次の単語も数詞または単位なら改行を避ける
                        if i + 1 < len(boundaries):
                            next_surface = boundaries[i + 1][1]
                            next_pos = boundaries[i + 1][2]
                            if next_pos == "名詞" and (
                                next_surface.isdigit()
                                or any(c in next_surface for c in "年月日時分秒")
                                or next_surface in "年月日時分秒"
                            ):
                                score *= 0.05  # 強く避ける
                                logger.debug(f"数詞の後に数詞/単位が続くため改行を避ける: {surface} -> {next_surface}")
                    else:
                        score *= 1.5
                        logger.debug(f"名詞の後なので改行しやすい: {surface}")

                # 助詞の後も改行しやすい（「かな」「ね」「よ」などの終助詞）
                if pos_tag == "助詞":
                    score *= 1.8
                    logger.debug(f"助詞の後なので改行しやすい: {surface}")

                # 助詞の前は改行しやすい
                if i + 1 < len(boundaries) and boundaries[i + 1][2] == "助詞":
                    score *= 2.0
                    logger.debug(f"次が助詞なので改行しやすい: {boundaries[i + 1][1]}")

                # 動詞・形容詞の後も改行しやすい
                if pos_tag in ["動詞", "形容詞"]:
                    score *= 1.3
                    logger.debug(f"{pos_tag}の後なので改行しやすい: {surface}")

                break

        return score

    @staticmethod
    def can_break_at(text: str, position: int) -> bool:
        """指定位置で改行可能かチェック

        Args:
            text: テキスト
            position: 改行位置（0-based、文字の間の位置）

        Returns:
            改行可能かどうか
        """
        if position <= 0 or position >= len(text):
            return False

        # 禁則処理チェック
        # 次の文字が行頭禁則文字
        if position < len(text) and text[position] in JapaneseLineBreakRules.LINE_START_NG:
            logger.debug(f"行頭禁則: '{text[position]}' at position {position}")
            return False

        # 前の文字が行末禁則文字
        if position > 0 and text[position - 1] in JapaneseLineBreakRules.LINE_END_NG:
            logger.debug(f"行末禁則: '{text[position-1]}' at position {position-1}")
            return False

        # 英単語の途中チェック
        if position > 0 and position < len(text):
            prev_char = text[position - 1]
            next_char = text[position]

            # ASCII文字のアルファベットの連続（日本語文字は除外）
            if prev_char.isascii() and prev_char.isalpha() and next_char.isascii() and next_char.isalpha():
                logger.debug(f"英単語の途中: '{prev_char}{next_char}' at position {position}")
                return False

            # 数字の連続
            if prev_char.isdigit() and next_char.isdigit():
                logger.debug(f"数字の途中: '{prev_char}{next_char}' at position {position}")
                return False

        # 分割禁止パターンのチェック
        for pattern in JapaneseLineBreakRules.NO_BREAK_PATTERNS:
            # パターンを含む範囲を検索
            for match in pattern.finditer(text):
                if match.start() < position < match.end():
                    logger.debug(f"分割禁止パターン: '{match.group()}' at position {position}")
                    return False

        return True

    @classmethod
    def find_best_break_point(cls, text: str, max_length: int, search_range: int = 5) -> int:
        """最適な改行位置を見つける（形態素解析対応）

        Args:
            text: テキスト
            max_length: 最大文字数
            search_range: 前後の探索範囲

        Returns:
            最適な改行位置
        """
        # テキストが短い場合
        if max_length >= len(text):
            return len(text)

        logger.info(f"find_best_break_point: text='{text}', max_length={max_length}")

        # 0. 形態素解析による単語境界と品詞情報を取得
        boundaries_with_pos = cls.get_word_boundaries_with_pos(text)

        # 1. 品詞情報を使った最適な改行位置の選択
        if boundaries_with_pos:
            logger.debug(f"形態素解析による単語境界（品詞付き）: {[(b[0], b[1], b[2]) for b in boundaries_with_pos]}")

            # max_length以下の候補位置をスコア付きで評価
            candidates = []
            for boundary, surface, pos_tag in boundaries_with_pos:
                if 0 < boundary <= max_length:
                    if cls.can_break_at(text, boundary):
                        score = cls.evaluate_break_position(boundaries_with_pos, boundary)
                        candidates.append((boundary, score))
                        logger.debug(f"候補位置 {boundary}: スコア {score}")

            # スコアが一定以上の候補から、max_lengthに最も近い位置を選択
            if candidates:
                # スコアが0.5以上の候補を選択（極端に悪い位置は避ける）
                good_candidates = [(pos, score) for pos, score in candidates if score >= 0.5]

                if good_candidates:
                    # max_lengthに最も近い位置を選択
                    good_candidates.sort(key=lambda x: -x[0])  # 位置降順（大きい方が優先）
                    best_boundary = good_candidates[0][0]
                    logger.debug(f"最適な改行位置: {best_boundary} (スコア: {good_candidates[0][1]})")
                else:
                    # 良い候補がない場合は、最もスコアが高い位置を選択
                    candidates.sort(key=lambda x: (-x[1], -x[0]))  # スコア降順、位置降順
                    best_boundary = candidates[0][0]
                    logger.debug(f"最適な改行位置（スコア優先）: {best_boundary} (スコア: {candidates[0][1]})")

                return best_boundary

        # 2. 指定位置で改行可能かチェック
        if cls.can_break_at(text, max_length):
            # 助詞の前での改行を優先チェック
            if max_length < len(text) and text[max_length] in cls.PARTICLES:
                logger.debug(f"助詞 '{text[max_length]}' の前で改行")
                return max_length
            return max_length

        # 3. 前方向のみ探索（1行あたりの文字数を最優先）
        # まず助詞を優先して探す
        logger.debug(f"助詞での改行位置を探索中: text='{text}', max_length={max_length}")
        for offset in range(1, min(search_range + 1, max_length)):
            pos = max_length - offset
            if pos > 0 and pos < len(text) and text[pos] in cls.PARTICLES:
                logger.debug(f"位置{pos}で助詞'{text[pos]}'を発見")
                if cls.can_break_at(text, pos):
                    logger.debug(f"助詞 '{text[pos]}' の前で改行: {max_length} -> {pos}")
                    return pos
                else:
                    logger.debug(f"位置{pos}では改行不可（禁則処理）")

        # 4. 助詞が見つからない場合は通常の探索
        for offset in range(1, min(search_range + 1, max_length)):
            pos = max_length - offset
            if pos > 0 and cls.can_break_at(text, pos):
                logger.debug(f"改行位置を前方に調整: {max_length} -> {pos}")
                return pos

        # 5. 句読点を探す（さらに前方向）
        punctuations = "。、．，！？"
        for i in range(max_length - 1, max(0, max_length - 20), -1):
            if text[i] in punctuations:
                return i + 1  # 句読点の後で改行

        # 6. それでも見つからない場合は元の位置
        logger.warning(f"適切な改行位置が見つからず、強制的に位置{max_length}で改行")
        return max_length

    @classmethod
    def extract_line(cls, text: str, max_length: int) -> tuple[str, str]:
        """1行分のテキストを抽出

        Args:
            text: テキスト
            max_length: 最大文字数

        Returns:
            (抽出した行, 残りのテキスト)
        """
        logger.debug(f"extract_line: text='{text}', max_length={max_length}")

        if not text:
            return "", ""

        break_pos = cls.find_best_break_point(text, max_length)
        logger.debug(f"break_pos={break_pos}")

        line = text[:break_pos]
        remaining = text[break_pos:]

        # 行頭の空白を削除
        remaining = remaining.lstrip()

        logger.debug(f"extracted line='{line}', remaining='{remaining}'")

        return line, remaining
