"""
検索ベースLCSハイブリッドアプローチのゲートウェイ実装

長大なテキストに対する短い検索の場合に、特徴語クラスタリングで
候補範囲を絞り込んでからLCSを実行することで、計算量を大幅に削減する。
"""

from typing import List, Optional, Dict, Any, Tuple
import re
from uuid import uuid4
from janome.tokenizer import Tokenizer
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult
from domain.value_objects import TimeRange
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from domain.use_cases.time_range_calculator_lcs import TimeRangeCalculatorLCS
from use_cases.interfaces.text_processor_gateway import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class FeatureWord:
    """特徴語を表すクラス"""
    def __init__(self, word: str, pos: str, score: float):
        self.word = word
        self.pos = pos  # 品詞
        self.score = score


class Cluster:
    """特徴語のクラスタを表すクラス"""
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
        self.words: List[Dict] = []
        self.score = 0.0
        self.unique_word_count = 0


class SearchBasedLCSTextProcessorGateway(ITextProcessorGateway):
    """
    検索ベースLCSハイブリッドアプローチのゲートウェイ
    
    長さが大きく異なるテキストの比較時に、特徴語検索で候補範囲を
    絞り込んでからLCSを実行する。
    """
    
    def __init__(self):
        self.tokenizer = Tokenizer()
        self.detector = TextDifferenceDetectorLCS()
        self.calculator = TimeRangeCalculatorLCS()
        self._transcription_result_cache = {}
        
        # 閾値設定
        self.length_ratio_threshold = 0.1  # 10%以下ならハイブリッド検索を使用
        self.window_size = 500  # クラスタリングのウィンドウサイズ
        self.context_margin = 200  # LCS実行時のコンテキストマージン
        self.max_clusters = 3  # 評価するクラスタの最大数
        self.min_match_length = 2  # 最小マッチ長を2文字に変更
        # 1文字（助詞など）は除外するが、2文字の重要語は保持
        # 「AI」「IT」「問題」「解決」など重要な2文字単語を逃さないため
        
        logger.info("SearchBasedLCSTextProcessorGatewayを初期化しました")
    
    def normalize_for_comparison(self, text: str) -> str:
        """比較用にテキストを正規化"""
        # 改行を除去
        normalized = text.replace('\n', '').replace('\r', '')
        
        # 全角スペースを半角に統一
        normalized = normalized.replace('　', ' ')
        
        # 日本語文字間のスペースを除去
        normalized = re.sub(r'([ぁ-んァ-ヶー一-龯])\s+([ぁ-んァ-ヶー一-龯])', r'\1\2', normalized)
        
        # 先頭・末尾のスペースを除去
        normalized = normalized.strip()
        
        # 句読点の後のスペースを除去
        normalized = re.sub(r'([、。])\s*', r'\1', normalized)
        
        return normalized
    
    def _extract_context_hints(self, text: str) -> Tuple[List[Dict], str]:
        """
        {前後の単語}形式のヒントを抽出する
        """
        pattern = r'\{([^}]+)\}'
        hints = []
        
        for match in re.finditer(pattern, text):
            hint_text = match.group(1)
            position = match.start()
            
            # ヒントの前後を判定
            before_text = text[:position].strip()
            after_text = text[match.end():].strip()
            
            if before_text and before_text[-1] not in '。、':
                # 前の文脈
                target_start = max(0, position - 20)
                target_word = text[target_start:position].strip().split()[-1] if text[target_start:position].strip() else ""
                if target_word:
                    hints.append({
                        'type': 'before',
                        'hint': hint_text,
                        'target': target_word,
                        'position': position
                    })
            elif after_text and after_text[0] not in '。、':
                # 後の文脈
                target_end = min(len(text), match.end() + 20)
                target_text = text[match.end():target_end].strip()
                target_word = target_text.split()[0] if target_text else ""
                if target_word:
                    hints.append({
                        'type': 'after',
                        'hint': hint_text,
                        'target': target_word,
                        'position': position
                    })
        
        # ヒントを削除したクリーンなテキストも返す
        clean_text = re.sub(pattern, '', text)
        return hints, clean_text
    
    def _has_separator(self, text: str) -> bool:
        """テキストにセパレータが含まれているかチェック"""
        separator_patterns = ['---', '——', '－－－']
        return any(sep in text for sep in separator_patterns)
    
    def _extract_feature_words(self, text: str) -> List[FeatureWord]:
        """
        編集テキストから特徴語を抽出し、重要度でスコアリング
        """
        feature_words = []
        
        # 形態素解析
        tokens = self.tokenizer.tokenize(text)
        
        for token in tokens:
            word = token.surface
            features = token.part_of_speech.split(',')
            pos = features[0]
            pos_detail = features[1] if len(features) > 1 else ""
            
            # 特徴語の条件
            if pos in ['名詞', '動詞', '形容詞'] and len(word) >= 2:
                # スコアリング
                if pos_detail in ['固有名詞', 'サ変接続', '形容動詞語幹']:
                    score = 3.0
                elif pos == '名詞':
                    score = 2.0
                else:
                    score = 1.0
                
                feature_words.append(FeatureWord(word, pos, score))
        
        # 重複除去とソート
        unique_words = {}
        for fw in feature_words:
            if fw.word not in unique_words or unique_words[fw.word].score < fw.score:
                unique_words[fw.word] = fw
        
        return sorted(unique_words.values(), key=lambda x: x.score, reverse=True)
    
    def _find_feature_positions(self, full_text: str, feature_words: List[FeatureWord]) -> Dict[str, List[int]]:
        """
        元テキストで各特徴語の出現位置を検索
        """
        positions = {}
        for fw in feature_words:
            word = fw.word
            positions[word] = []
            start = 0
            while True:
                pos = full_text.find(word, start)
                if pos == -1:
                    break
                positions[word].append(pos)
                start = pos + 1
        return positions
    
    def _create_feature_clusters(self, feature_positions: Dict[str, List[int]], feature_words: List[FeatureWord]) -> List[Cluster]:
        """
        特徴語の出現位置からクラスタを作成
        """
        # 特徴語辞書を作成
        feature_words_dict = {fw.word: fw for fw in feature_words}
        
        # すべての特徴語位置を収集
        all_positions = []
        for word, positions in feature_positions.items():
            for pos in positions:
                all_positions.append({
                    'word': word,
                    'position': pos,
                    'score': feature_words_dict[word].score
                })
        
        # 位置でソート
        all_positions.sort(key=lambda x: x['position'])
        
        # クラスタリング
        clusters = []
        for anchor in all_positions:
            # このアンカーを中心としたウィンドウ内の特徴語を収集
            cluster = Cluster(anchor['position'], anchor['position'])
            
            for pos_info in all_positions:
                if cluster.start <= pos_info['position'] <= cluster.start + self.window_size:
                    cluster.words.append(pos_info)
                    cluster.end = max(cluster.end, pos_info['position'])
            
            # クラスタのスコア計算
            unique_words = set(w['word'] for w in cluster.words)
            cluster.unique_word_count = len(unique_words)
            total_score = sum(w['score'] for w in cluster.words)
            density = len(cluster.words) / max(1, cluster.end - cluster.start)
            
            cluster.score = total_score * cluster.unique_word_count * density
            clusters.append(cluster)
        
        # 重複するクラスタをマージ
        merged_clusters = []
        for cluster in sorted(clusters, key=lambda x: x.score, reverse=True):
            # 既存のクラスタと重複チェック
            overlaps = False
            for existing in merged_clusters:
                if not (cluster.end < existing.start or cluster.start > existing.end):
                    overlaps = True
                    break
            
            if not overlaps:
                merged_clusters.append(cluster)
            
            if len(merged_clusters) >= self.max_clusters:
                break
        
        return merged_clusters
    
    def _evaluate_lcs_result(self, diff: TextDifference) -> float:
        """
        LCS結果を評価してスコアを返す
        """
        # UNCHANGEDブロックの統計を計算
        unchanged_blocks = [
            (text, positions) 
            for diff_type, text, positions in diff.differences
            if diff_type == DifferenceType.UNCHANGED
        ]
        
        if not unchanged_blocks:
            return 0.0
        
        # 最小マッチ長以上のブロックのみをカウント
        valid_blocks = [(text, pos) for text, pos in unchanged_blocks if len(text) >= self.min_match_length]
        
        if not valid_blocks:
            return 0.0
        
        # 総LCS長（有効なブロックのみ）
        lcs_length = sum(len(text) for text, _ in valid_blocks)
        
        # 最長連続マッチを見つける
        max_continuous = max(len(text) for text, _ in valid_blocks) if valid_blocks else 0
        
        # 断片化度（ブロック数 / 最大可能ブロック数）
        fragmentation = len(valid_blocks) / max(1, lcs_length)
        
        # 短いマッチに対するペナルティ
        short_match_penalty = sum(1 for text, _ in unchanged_blocks if len(text) < self.min_match_length) * 0.1
        
        # 評価スコア計算
        evaluation = (
            lcs_length * 0.4 +              # LCS長の重み
            max_continuous * 0.4 +          # 連続性の重み
            (1 / max(fragmentation, 0.001)) * 0.2  # 断片化度の逆数の重み
        ) - short_match_penalty
        
        return max(0, evaluation)
    
    def _hybrid_search(self, full_text: str, edited_text: str, context_hints: List[Dict], skip_normalization: bool) -> TextDifference:
        """
        ハイブリッド検索アプローチで差分を検出
        """
        # 編集テキストも正規化
        normalized_edited = self.normalize_for_comparison(edited_text) if not skip_normalization else edited_text
        logger.info(f"編集テキスト正規化: {len(edited_text)}文字 → {len(normalized_edited)}文字")
        
        # 特徴語を抽出（正規化後のテキストから）
        feature_words = self._extract_feature_words(normalized_edited)
        logger.info(f"特徴語を{len(feature_words)}個抽出: {[fw.word for fw in feature_words[:5]]}")
        
        if not feature_words:
            # 特徴語がない場合は従来の検索にフォールバック
            return self._traditional_search(full_text, normalized_edited, skip_normalization)
        
        # 特徴語の位置を検索
        feature_positions = self._find_feature_positions(full_text, feature_words)
        
        # クラスタリング
        clusters = self._create_feature_clusters(feature_positions, feature_words)
        logger.info(f"クラスタを{len(clusters)}個作成: スコア={[c.score for c in clusters]}")
        
        if not clusters:
            # クラスタが見つからない場合は全文検索
            return self._traditional_search(full_text, normalized_edited, skip_normalization)
        
        # 各クラスタでLCSを実行し、最良の結果を選択
        best_result = None
        best_evaluation = 0
        best_offset = 0
        
        for cluster in clusters:
            # クラスタ範囲を前後に拡張
            start = max(0, cluster.start - self.context_margin)
            end = min(len(full_text), cluster.end + self.context_margin)
            
            partial_text = full_text[start:end]
            
            # この部分テキストでLCS実行
            partial_diff = self._traditional_search(partial_text, normalized_edited, skip_normalization)
            
            # 結果の評価
            if partial_diff.differences:
                evaluation = self._evaluate_lcs_result(partial_diff)
                
                if evaluation > best_evaluation:
                    best_evaluation = evaluation
                    best_offset = start
                    best_result = partial_diff
        
        if best_result:
            # 最良の結果に対して位置情報を追加
            adjusted_differences = []
            
            # 正規化されたテキストと元のテキストのマッピングを作成
            normalized_full = self.normalize_for_comparison(full_text[best_offset:best_offset + self.window_size * 2])
            
            for diff_type, text, _ in best_result.differences:
                # 短すぎるマッチをスキップ
                if diff_type == DifferenceType.UNCHANGED and len(text) < self.min_match_length:
                    logger.debug(f"短すぎるマッチをスキップ: '{text}' (長さ: {len(text)})")
                    continue
                    
                # 元のテキストでの実際の位置を計算
                positions = None
                if diff_type == DifferenceType.UNCHANGED:
                    # まず正確な位置で検索
                    search_start = best_offset
                    pos = full_text.find(text, search_start)
                    
                    if pos == -1:
                        # 見つからない場合は、正規化されたテキストで探す
                        normalized_text = self.normalize_for_comparison(text)
                        # 元のテキストの部分を正規化しながら検索
                        for i in range(search_start, min(len(full_text) - len(text) + 1, search_start + self.window_size * 2)):
                            # この位置から同じ長さの部分を正規化
                            candidate = full_text[i:i + len(text) + 10]  # 少し余裕を持たせる
                            normalized_candidate = self.normalize_for_comparison(candidate)
                            
                            if normalized_candidate.startswith(normalized_text):
                                # 正規化後に一致する場合、実際の長さを調整
                                actual_end = i
                                normalized_len = 0
                                for j in range(i, len(full_text)):
                                    if normalized_len >= len(normalized_text):
                                        break
                                    actual_end = j + 1
                                    normalized_len = len(self.normalize_for_comparison(full_text[i:j+1]))
                                
                                pos = i
                                positions = [(pos, actual_end)]
                                break
                    else:
                        positions = [(pos, pos + len(text))]
                
                adjusted_differences.append((diff_type, text, positions))
            
            return TextDifference(
                id=str(uuid4()),
                original_text=full_text,
                edited_text=edited_text,  # 元の編集テキストを保持
                differences=adjusted_differences
            )
        
        return TextDifference(
            id=str(uuid4()),
            original_text=full_text,
            edited_text=edited_text,  # 元の編集テキストを保持
            differences=[]
        )
    
    def _traditional_search(self, original_text: str, edited_text: str, skip_normalization: bool) -> TextDifference:
        """
        従来の検索ベース差分検出
        """
        # 正規化
        if not skip_normalization:
            normalized_original = self.normalize_for_comparison(original_text)
            normalized_edited = self.normalize_for_comparison(edited_text)
        else:
            normalized_original = original_text
            normalized_edited = edited_text
        
        # LCSベースの差分検出
        text_difference = self.detector.detect_differences(
            normalized_original, normalized_edited, None
        )
        
        # 元のテキストを保持
        text_difference.original_text = original_text
        text_difference.edited_text = edited_text
        
        return text_difference
    
    def find_differences(
        self,
        original_text: str,
        edited_text: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        テキストの差分を検出する
        
        長さの比率に応じて、純粋LCSまたはハイブリッド検索を使用する。
        """
        logger.info("検索ベースのLCS差分検出を開始します")
        
        # 文脈ヒントを抽出
        context_hints, clean_edited_text = self._extract_context_hints(edited_text)
        
        # セパレータチェック
        if self._has_separator(clean_edited_text):
            return self._process_with_separators(original_text, clean_edited_text, skip_normalization)
        
        # 長さの比率を計算（正規化前のテキストで）
        length_ratio = len(clean_edited_text) / max(len(original_text), 1)
        
        if length_ratio >= self.length_ratio_threshold:
            # 純粋LCSを使用
            logger.info(f"長さの比率 {length_ratio:.1%} >= {self.length_ratio_threshold:.1%}、純粋LCSを使用")
            return self._traditional_search(original_text, clean_edited_text, skip_normalization)
        else:
            # ハイブリッド検索を使用
            logger.info(f"長さの比率 {length_ratio:.1%} < {self.length_ratio_threshold:.1%}、ハイブリッド検索を使用")
            return self._hybrid_search(original_text, clean_edited_text, context_hints, skip_normalization)
    
    def _process_with_separators(self, full_text: str, edited_text: str, skip_normalization: bool) -> TextDifference:
        """
        セパレータで区切られたテキストを処理する
        """
        # 区切り文字を特定
        separator_patterns = ['---', '——', '－－－']
        used_separator = None
        for pattern in separator_patterns:
            if pattern in edited_text:
                used_separator = pattern
                break
        
        if not used_separator:
            # セパレータなしの場合は通常処理
            return self._hybrid_search(full_text, edited_text, [], skip_normalization)
        
        # テキストを分割
        blocks = edited_text.split(used_separator)
        all_differences = []
        last_end_position = 0
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            # 前のブロックの終了位置以降から検索
            search_text = full_text[last_end_position:]
            
            # このブロックの差分を検出
            block_diff = self._hybrid_search(search_text, block, [], skip_normalization)
            
            # 位置をオフセット調整
            for diff_type, text, positions in block_diff.differences:
                adjusted_positions = None
                if positions:
                    adjusted_positions = [
                        (pos[0] + last_end_position, pos[1] + last_end_position)
                        for pos in positions
                    ]
                all_differences.append((diff_type, text, adjusted_positions))
            
            # 次の検索開始位置を更新
            if block_diff.differences:
                # 最後のUNCHANGEDブロックの終了位置を探す
                for diff_type, _, positions in reversed(block_diff.differences):
                    if diff_type == DifferenceType.UNCHANGED and positions:
                        last_end_position = positions[-1][1] + last_end_position
                        break
        
        return TextDifference(
            id=str(uuid4()),
            original_text=full_text,
            edited_text=edited_text,
            differences=all_differences
        )
    
    # 以下、他のメソッドは NormalizedLCSTextProcessorGateway と同じ
    def get_time_ranges(
        self, text_difference: TextDifference, transcription_result: TranscriptionResult
    ) -> List[TimeRange]:
        """差分情報から時間範囲を計算"""
        logger.info("時間範囲の計算を開始します")
        
        # CharacterArrayBuilderで再構築したテキストを使用
        # これにより、文字位置が完全に一致する
        from domain.use_cases.character_array_builder import CharacterArrayBuilder
        builder = CharacterArrayBuilder()
        char_array, full_text = builder.build_from_transcription(transcription_result)
        
        logger.info(f"CharacterArrayBuilderで再構築: {len(full_text)}文字")
        normalized_original = self.normalize_for_comparison(full_text)
        
        # 差分ブロックを取得（再計算が必要）
        # 注意：正規化されたテキストではなく、元のテキストを使用する
        # ただし、このテキストはCharacterArrayBuilderで再構築されたものと同じである必要がある
        _, diff_blocks = self.detector.detect_differences_with_blocks(
            full_text,  # CharacterArrayBuilderで再構築されたテキスト
            text_difference.edited_text,  # 編集テキスト
            transcription_result
        )
        
        # 時間範囲を計算
        time_ranges = self.calculator.calculate_from_blocks(diff_blocks)
        
        # マージ（隣接する範囲を結合）
        merged_ranges = self.calculator.merge_adjacent_ranges(time_ranges, gap_threshold=0.5)
        
        # TimeRangeオブジェクトに変換
        result = [TimeRange(start=r.start, end=r.end) for r in merged_ranges]
        
        logger.info(f"時間範囲を計算しました: {len(result)}個の範囲")
        return result
    
    def apply_boundary_adjustments(self, text: str, time_ranges: list[TimeRange]) -> tuple[str, list[TimeRange]]:
        """境界調整マーカーを適用"""
        return text, time_ranges
    
    def normalize_text(self, text: str) -> str:
        """テキストを正規化"""
        return self.normalize_for_comparison(text)
    
    def search_text(
        self, query: str, transcription_result: TranscriptionResult, case_sensitive: bool = False
    ) -> list[tuple[str, TimeRange]]:
        """文字起こし結果からテキストを検索"""
        # レガシー形式の場合はセグメントから結合
        if hasattr(transcription_result, 'text'):
            full_text = transcription_result.text
        else:
            full_text = "".join(seg.text for seg in transcription_result.segments)
        normalized_text = self.normalize_for_comparison(full_text)
        normalized_query = self.normalize_for_comparison(query)
        
        if not case_sensitive:
            normalized_text = normalized_text.lower()
            normalized_query = normalized_query.lower()
        
        results = []
        start = 0
        while True:
            pos = normalized_text.find(normalized_query, start)
            if pos == -1:
                break
            
            if transcription_result.segments:
                total_duration = transcription_result.segments[-1].end
                char_duration = total_duration / len(normalized_text) if normalized_text else 0
                time_range = TimeRange(
                    start=pos * char_duration,
                    end=(pos + len(normalized_query)) * char_duration
                )
                results.append((transcription_result.text[pos:pos + len(query)], time_range))
            
            start = pos + 1
        
        return results