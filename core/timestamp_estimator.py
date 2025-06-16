"""
タイムスタンプ推定モジュール
"""
from typing import List, Tuple, Optional, Any
from utils.logging import get_logger

logger = get_logger(__name__)


class TimestampEstimator:
    """タイムスタンプ推定クラス"""
    
    def estimate_timestamp_fallback(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[float, float]:
        """
        フォールバック階層アプローチでタイムスタンプを推定
        
        Args:
            seg: 現在のセグメント
            word_idx: word のインデックス
            word_text: word のテキスト
            
        Returns:
            (推定開始時間, 推定終了時間)
        """
        # Step 1: 近隣の有効なタイムスタンプから推定
        result = self._estimate_from_nearby_timestamps(seg, word_idx, word_text)
        if result[0] is not None:
            return result
        
        # Step 2: セグメント内の発話速度から推定
        result = self._estimate_from_speech_rate(seg, word_idx, word_text)
        if result[0] is not None:
            return result
        
        # Step 3: セグメント境界から推定（改善版）
        result = self._estimate_from_segment_bounds(seg, word_idx, word_text)
        return result
    
    def _estimate_from_nearby_timestamps(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        近隣の有効なタイムスタンプから推定
        
        Returns:
            (推定開始時間, 推定終了時間) または (None, None)
        """
        # 前後の有効なタイムスタンプを収集
        prev_timestamps = []
        next_timestamps = []
        
        # 前方検索（最大10個まで拡張）
        for prev_idx in range(max(0, word_idx - 10), word_idx):
            prev_word = seg.words[prev_idx]
            ts_start, ts_end = self._extract_timestamp(prev_word)
            if ts_start is not None and ts_end is not None:
                prev_timestamps.append((prev_idx, ts_start, ts_end))
        
        # 後方検索（最大10個まで拡張）
        for next_idx in range(word_idx + 1, min(len(seg.words), word_idx + 11)):
            next_word = seg.words[next_idx]
            ts_start, ts_end = self._extract_timestamp(next_word)
            if ts_start is not None and ts_end is not None:
                next_timestamps.append((next_idx, ts_start, ts_end))
        
        # 推定処理
        if prev_timestamps and next_timestamps:
            # 両方ある場合：線形補間
            prev_idx, prev_start, prev_end = prev_timestamps[-1]
            next_idx, next_start, next_end = next_timestamps[0]
            
            # より精密な補間（文字数も考慮）
            char_count_before = sum(len(self._get_word_text(seg.words[i])) 
                                  for i in range(prev_idx, word_idx))
            char_count_after = sum(len(self._get_word_text(seg.words[i])) 
                                 for i in range(word_idx + 1, next_idx + 1))
            char_count_current = len(word_text)
            
            total_chars = char_count_before + char_count_current + char_count_after
            if total_chars > 0:
                # 文字数ベースの位置比率
                position_ratio = char_count_before / total_chars
            else:
                # インデックスベースにフォールバック
                position_ratio = (word_idx - prev_idx) / (next_idx - prev_idx)
            
            # 時間を推定
            time_gap = next_start - prev_end
            estimated_start = prev_end + time_gap * position_ratio
            
            # 終了時間は局所的な平均発話速度から
            # 句読点の場合は特別処理
            if word_text in ['。', '、', '！', '？', '．', '，']:
                # 句読点は瞬間的（継続時間なし）
                estimated_end = estimated_start
            else:
                local_speed = (char_count_before + char_count_after) / (next_end - prev_start)
                if local_speed > 0:
                    estimated_duration = char_count_current / local_speed
                else:
                    estimated_duration = (prev_end - prev_start + next_end - next_start) / 2
                
                estimated_end = estimated_start + estimated_duration
            
            logger.debug(f"タイムスタンプを近隣から推定（補間）: {word_text} "
                        f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
            
        elif prev_timestamps:
            # 前のタイムスタンプのみ
            prev_idx, prev_start, prev_end = prev_timestamps[-1]
            
            # 句読点の特別処理
            if word_text in ['。', '、', '！', '？', '．', '，']:
                # 前の単語が異常に長い場合（APIが延ばしている可能性）
                prev_word = seg.words[prev_idx]
                prev_word_text = self._get_word_text(prev_word)
                prev_duration = prev_end - prev_start
                
                # 短い単語（2文字以下）で0.5秒以上は異常
                if len(prev_word_text) <= 2 and prev_duration > 0.5:
                    # さらに前の単語の終了時刻を使用
                    if prev_idx > 0:
                        prev_prev_word = seg.words[prev_idx - 1]
                        prev_prev_end = self._extract_timestamp(prev_prev_word)[1]
                        if prev_prev_end is not None:
                            estimated_start = prev_prev_end
                            estimated_end = prev_prev_end
                            logger.debug(f"句読点の前の単語が異常に長いため調整: {word_text} "
                                        f"前の単語「{prev_word_text}」({prev_duration:.3f}秒) "
                                        f"-> {estimated_start:.2f}秒")
                            return estimated_start, estimated_end
                
                # 通常の句読点処理
                estimated_start = prev_end
                estimated_end = prev_end  # 句読点は瞬間的
                logger.debug(f"句読点のタイムスタンプを推定: {word_text} "
                            f"({estimated_start:.2f}秒)")
                return estimated_start, estimated_end
            
            # 前の単語からの文字数
            char_count = sum(len(self._get_word_text(seg.words[i])) 
                           for i in range(prev_idx + 1, word_idx + 1))
            
            # 前の単語の発話速度を使用
            prev_duration = prev_end - prev_start
            prev_chars = len(self._get_word_text(seg.words[prev_idx]))
            
            if prev_chars > 0 and prev_duration > 0:
                char_per_sec = prev_chars / prev_duration
                estimated_duration = len(word_text) / char_per_sec
                estimated_start = prev_end + 0.05  # 小さなギャップ
            else:
                estimated_duration = 0.2  # デフォルト
                estimated_start = prev_end + 0.1
            
            estimated_end = estimated_start + estimated_duration
            
            logger.debug(f"タイムスタンプを前方から推定: {word_text} "
                        f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
            
        elif next_timestamps:
            # 後のタイムスタンプのみ
            next_idx, next_start, next_end = next_timestamps[0]
            
            # 次の単語までの文字数
            char_count = sum(len(self._get_word_text(seg.words[i])) 
                           for i in range(word_idx, next_idx))
            
            # 次の単語の発話速度を使用
            next_duration = next_end - next_start
            next_chars = len(self._get_word_text(seg.words[next_idx]))
            
            if next_chars > 0 and next_duration > 0:
                char_per_sec = next_chars / next_duration
                estimated_duration = len(word_text) / char_per_sec
                estimated_end = next_start - 0.05  # 小さなギャップ
            else:
                estimated_duration = 0.2  # デフォルト
                estimated_end = next_start - 0.1
            
            estimated_start = estimated_end - estimated_duration
            
            logger.debug(f"タイムスタンプを後方から推定: {word_text} "
                        f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
            return estimated_start, estimated_end
        
        # 近隣にタイムスタンプがない場合
        return None, None
    
    def _estimate_from_speech_rate(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        セグメント内の発話速度から推定
        
        Returns:
            (推定開始時間, 推定終了時間) または (None, None)
        """
        # 句読点の特別処理
        if word_text in ['。', '、', '！', '？', '．', '，']:
            # 句読点は前のwordの直後に配置
            if word_idx > 0:
                prev_word = seg.words[word_idx - 1]
                prev_end = self._extract_timestamp(prev_word)[1]
                if prev_end is not None:
                    logger.debug(f"句読点を発話速度推定でスキップ: {word_text} -> {prev_end}秒")
                    return prev_end, prev_end
            # 前のwordがない場合はセグメント開始
            return seg.start, seg.start
        # セグメント内の有効なタイムスタンプを持つwordを収集
        valid_words = []
        for i, word in enumerate(seg.words):
            ts_start, ts_end = self._extract_timestamp(word)
            if ts_start is not None and ts_end is not None:
                valid_words.append({
                    'index': i,
                    'text': self._get_word_text(word),
                    'start': ts_start,
                    'end': ts_end
                })
        
        if len(valid_words) < 2:
            # 発話速度を計算するには少なくとも2つの有効なwordが必要
            return None, None
        
        # 最初と最後の有効なタイムスタンプ
        first_valid = valid_words[0]
        last_valid = valid_words[-1]
        
        # 実際の発話範囲
        speech_start = first_valid['start']
        speech_end = last_valid['end']
        speech_duration = speech_end - speech_start
        
        # 総文字数を計算
        total_chars = sum(len(w['text']) for w in valid_words)
        
        if speech_duration > 0 and total_chars > 0:
            # 平均発話速度（文字/秒）
            avg_char_per_sec = total_chars / speech_duration
            
            # 現在のwordまでの文字数
            chars_before = sum(len(self._get_word_text(seg.words[i])) 
                             for i in range(word_idx))
            
            # 推定時間
            if word_idx < first_valid['index']:
                # 最初の有効タイムスタンプより前
                # 発話開始前の時間を推定
                chars_to_first = sum(len(self._get_word_text(seg.words[i])) 
                                   for i in range(word_idx, first_valid['index']))
                time_before = chars_to_first / avg_char_per_sec
                estimated_start = max(seg.start, speech_start - time_before)
                estimated_duration = len(word_text) / avg_char_per_sec
                estimated_end = estimated_start + estimated_duration
            else:
                # 通常の推定
                estimated_time = speech_start + (chars_before / avg_char_per_sec)
                estimated_duration = len(word_text) / avg_char_per_sec
                estimated_start = estimated_time
                estimated_end = estimated_start + estimated_duration
            
            logger.debug(f"タイムスタンプを発話速度から推定: {word_text} "
                        f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒) "
                        f"[速度: {avg_char_per_sec:.1f}文字/秒]")
            return estimated_start, estimated_end
        
        return None, None
    
    def _estimate_from_segment_bounds(
        self,
        seg: 'TranscriptionSegment',
        word_idx: int,
        word_text: str
    ) -> Tuple[float, float]:
        """
        セグメント境界から推定（改善版）
        最終手段として使用
        
        Returns:
            (推定開始時間, 推定終了時間)
        """
        # セグメント内の最初と最後の有効なタイムスタンプを探す
        first_valid_time = None
        last_valid_time = None
        
        for word in seg.words:
            ts_start, ts_end = self._extract_timestamp(word)
            if ts_start is not None:
                if first_valid_time is None:
                    first_valid_time = ts_start
                last_valid_time = ts_end
        
        # 実際の発話範囲を推定
        if first_valid_time is not None and last_valid_time is not None:
            # 有効なタイムスタンプがある場合
            speech_start = first_valid_time
            speech_end = last_valid_time
            speech_duration = speech_end - speech_start
        else:
            # 全くタイムスタンプがない場合（最悪のケース）
            # セグメントの前後に少し余裕を持たせる
            speech_start = seg.start + 0.5
            speech_end = seg.end - 0.5
            speech_duration = speech_end - speech_start
        
        # 位置比率で推定
        if len(seg.words) > 0:
            word_ratio = word_idx / len(seg.words)
            estimated_start = speech_start + speech_duration * word_ratio
            
            # 単純な長さ推定
            avg_word_duration = speech_duration / len(seg.words)
            estimated_end = estimated_start + avg_word_duration
        else:
            # フォールバックのフォールバック
            estimated_start = seg.start
            estimated_end = seg.start + 0.2
        
        logger.debug(f"タイムスタンプをセグメント境界から推定（最終手段）: {word_text} "
                     f"({estimated_start:.2f}秒 - {estimated_end:.2f}秒)")
        return estimated_start, estimated_end
    
    def _extract_timestamp(self, word: Any) -> Tuple[Optional[float], Optional[float]]:
        """
        wordオブジェクトからタイムスタンプを抽出
        
        Returns:
            (start, end) または (None, None)
        """
        if hasattr(word, 'start') and hasattr(word, 'end'):
            return word.start, word.end
        elif isinstance(word, dict):
            return word.get('start'), word.get('end')
        return None, None
    
    def _get_word_text(self, word: Any) -> str:
        """
        wordオブジェクトからテキストを取得
        
        Returns:
            wordのテキスト
        """
        if hasattr(word, 'word'):
            return word.word
        elif isinstance(word, dict):
            return word.get('word', '')
        return ''