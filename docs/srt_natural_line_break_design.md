# SRT字幕の自然な改行とクリップ同期設計書

## 1. 要件整理

### 1.1 自然な改行処理
- 単語の途中で切らない
- 日本語として自然な位置で改行
- 表示できない場合は次の字幕として分割

### 1.2 文字起こしタイムスタンプとの整合性
- 動画またはXMLと必ず同時出力
- 文字起こしで得たタイムスタンプに基づく
- 字幕出力をオプション化（チェックボックス）

## 2. 設計方針

### 2.1 自然な改行位置の判定

#### 日本語の改行ルール
```python
class JapaneseLineBreakRules:
    """日本語の禁則処理ルール"""
    
    # 行頭禁則文字（行の先頭に来てはいけない）
    LINE_START_NG = set('、。，．・？！゛゜ヽヾゝゞ々ー）］｝」』!),.:;?]}°′″℃％‰')
    
    # 行末禁則文字（行の末尾に来てはいけない）
    LINE_END_NG = set('（［｛「『([{')
    
    # 分割禁止文字列（数字と単位など）
    NO_BREAK_PATTERNS = [
        r'\d+[年月日時分秒]',  # 10年、5月、3日など
        r'\d+[％%]',          # 50％、100%など
        r'[A-Za-z]+\d+',      # ABC123など
    ]
    
    @staticmethod
    def can_break_at(text: str, position: int) -> bool:
        """指定位置で改行可能かチェック"""
        if position <= 0 or position >= len(text):
            return False
            
        # 禁則処理チェック
        if position < len(text) and text[position] in JapaneseLineBreakRules.LINE_START_NG:
            return False
        if position > 0 and text[position-1] in JapaneseLineBreakRules.LINE_END_NG:
            return False
            
        # 英単語の途中チェック
        if position > 0 and position < len(text):
            if text[position-1].isalnum() and text[position].isalnum():
                return False
                
        return True
    
    @staticmethod
    def find_best_break_point(text: str, max_length: int) -> int:
        """最適な改行位置を見つける"""
        # まず指定文字数の位置をチェック
        if max_length >= len(text):
            return len(text)
            
        # 指定位置から前後に探索
        for offset in range(min(5, max_length)):  # 最大5文字まで調整
            # 後ろ方向
            pos = max_length + offset
            if pos < len(text) and JapaneseLineBreakRules.can_break_at(text, pos):
                return pos
            
            # 前方向
            pos = max_length - offset
            if pos > 0 and JapaneseLineBreakRules.can_break_at(text, pos):
                return pos
                
        # 見つからない場合は元の位置
        return max_length
```

### 2.2 チャンク分割の改善

#### 動的チャンク生成
```python
def _split_text_into_display_chunks(self, text: str) -> list[str]:
    """表示可能な単位でチャンクを動的に生成"""
    chunks = []
    remaining_text = text
    
    while remaining_text:
        # 1チャンクの最大文字数
        max_chunk_chars = self.max_line_length * self.max_lines
        
        if len(remaining_text) <= max_chunk_chars:
            # 全て収まる場合
            chunks.append(remaining_text)
            break
        
        # 自然な位置でチャンクを分割
        chunk_text, remaining_text = self._extract_natural_chunk(
            remaining_text, self.max_line_length, self.max_lines
        )
        chunks.append(chunk_text)
    
    return chunks

def _extract_natural_chunk(self, text: str, max_line_length: int, max_lines: int) -> tuple[str, str]:
    """自然な位置で1チャンク分のテキストを抽出"""
    lines = []
    remaining = text
    
    for line_num in range(max_lines):
        if not remaining:
            break
            
        # この行の最適な改行位置を見つける
        if len(remaining) <= max_line_length:
            lines.append(remaining)
            remaining = ""
        else:
            break_pos = JapaneseLineBreakRules.find_best_break_point(remaining, max_line_length)
            lines.append(remaining[:break_pos])
            remaining = remaining[break_pos:]
    
    chunk_text = "\n".join(lines)
    return chunk_text, remaining
```

### 2.3 字幕出力のUI改善

#### 出力形式の統合
```python
# ui/components.py の修正案

def show_export_settings() -> tuple[str, str, bool, int]:
    """エクスポート設定UI（字幕オプション追加）"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        process_type = st.radio(
            "処理方法",
            ["切り抜きのみ", "無音削除付き"],
            index=1,
        )
    
    with col2:
        # 主要な出力形式
        primary_format = st.radio(
            "出力形式",
            ["動画ファイル", "FCPXMLファイル", "Premiere Pro XML"],
            index=1,
        )
        
        # 字幕も同時出力するかのチェックボックス
        export_srt = st.checkbox(
            "SRT字幕も同時出力",
            value=True,
            help="動画またはXMLと同じタイミングでSRT字幕を出力します"
        )
    
    with col3:
        timeline_fps = st.number_input(
            "フレームレート",
            min_value=24,
            max_value=60,
            value=30,
            step=1,
        )
    
    return process_type, primary_format, export_srt, timeline_fps
```

### 2.4 処理フローの変更

#### 現在のフロー
```
1. 出力形式を選択（動画/FCPXML/Premiere/SRT）
2. 選択した形式のみ出力
```

#### 新しいフロー
```
1. 主要出力形式を選択（動画/FCPXML/Premiere）
2. SRT字幕の同時出力有無をチェックボックスで選択
3. 主要形式を出力
4. SRT選択時は同じタイミング情報を使用して字幕も出力
```

## 3. 実装手順

### 3.1 Phase 1: 自然な改行処理
1. `JapaneseLineBreakRules`クラスの実装
2. `_split_text_into_display_chunks`メソッドの実装
3. `_format_chunk_with_line_breaks`の削除（不要になる）

### 3.2 Phase 2: UI改善
1. `show_export_settings`の修正
2. 出力形式選択ロジックの変更
3. SRTを別形式から従属的な出力に変更


## 4. メリット

### 4.1 ユーザビリティ
- 自然な日本語表示
- 読みやすい字幕
- 簡潔なUI

### 4.2 技術的メリット
- 文字起こしタイムスタンプの正確な反映
- コードの簡潔化
- 保守性の向上

## 5. 考慮事項

### 5.1 後方互換性
- 既存の「SRT字幕」単独出力オプションは廃止
- 移行期間中は両方サポートする案も検討

### 5.2 パフォーマンス
- 動的チャンク生成による処理時間への影響
- 大量テキストでのテスト必要

### 5.3 国際化
- 英語など他言語での改行ルール
- 将来的な拡張性