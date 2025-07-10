# レガシー形式削除計画

## 概要
`core.transcription.TranscriptionResult`（レガシー形式）を完全に削除し、`domain.entities.transcription.TranscriptionResult`（ドメインエンティティ）に統一する。

## 現状分析

### レガシー形式の問題点
1. **データ構造の不整合**: セグメントとワードが辞書形式で混在
2. **型安全性の欠如**: 辞書アクセスによるエラーの頻発
3. **重複実装**: 同じ機能が複数箇所に散在
4. **テストの困難さ**: 辞書形式のためモックが複雑

### 主要な依存箇所
1. **文字起こしゲートウェイ** (`adapters/gateways/transcription/transcription_gateway.py`)
2. **テキスト処理ゲートウェイ** (`adapters/gateways/text_processing/*`)
3. **エクスポート処理** (`core/export.py`, `core/srt_exporter.py`)
4. **UIコンポーネント** (`ui/components.py`)
5. **メインアプリケーション** (`main.py`)

## 移行戦略

### フェーズ1: データ変換層の作成
1. **TranscriptionConverter**を強化
   - レガシー形式 → ドメインエンティティの変換を完全サポート
   - ドメインエンティティ → レガシー形式の逆変換（一時的）

### フェーズ2: ゲートウェイ層の移行
1. **TranscriptionGateway**をドメインエンティティベースに変更
2. **TextProcessorGateway**群をドメインエンティティ対応に
3. 各ゲートウェイ内でのレガシー形式使用を排除

### フェーズ3: ビジネスロジックの移行
1. **CharacterArrayBuilder**の修正
   - 辞書アクセスを排除
   - 型安全なWordオブジェクトを使用
2. **TimeRangeCalculator**の更新
3. **エクスポート処理**の更新

### フェーズ4: UI層の移行
1. **main.py**での直接的なレガシー形式使用を排除
2. **components.py**をドメインエンティティベースに
3. セッション状態管理の更新

### フェーズ5: レガシーコードの削除
1. `core/transcription.py`の削除
2. `core/transcription_api.py`の削除または大幅リファクタリング
3. 不要なテストコードの削除

## 実装詳細

### 1. TranscriptionConverterの強化

```python
class TranscriptionConverter:
    """レガシー形式とドメインエンティティの相互変換"""
    
    @staticmethod
    def from_legacy(legacy_result) -> TranscriptionResult:
        """レガシー形式からドメインエンティティへ変換"""
        segments = []
        for seg in legacy_result.segments:
            words = []
            if hasattr(seg, 'words') and seg.words:
                for w in seg.words:
                    word = Word(
                        word=w.get('word') or w.get('text', ''),
                        start=w.get('start', 0.0),
                        end=w.get('end', 0.0),
                        confidence=w.get('confidence') or w.get('score')
                    )
                    words.append(word)
            
            segment = TranscriptionSegment(
                id=str(getattr(seg, 'id', 0)),
                text=seg.text,
                start=seg.start,
                end=seg.end,
                words=words
            )
            segments.append(segment)
        
        return TranscriptionResult(
            id=str(uuid4()),
            video_id=getattr(legacy_result, 'video_id', 'unknown'),
            segments=segments,
            language=legacy_result.language,
            duration=segments[-1].end if segments else 0.0
        )
    
    @staticmethod
    def to_legacy(domain_result: TranscriptionResult):
        """ドメインエンティティからレガシー形式へ（一時的）"""
        # 移行期間中のみ必要
        pass
```

### 2. CharacterArrayBuilderの修正

```python
def _build_from_segment(self, segment: TranscriptionSegment, position: int) -> List[CharInfo]:
    """セグメントから文字配列を構築"""
    chars = []
    
    if segment.has_word_level_timestamps:
        # Wordオブジェクトとして直接アクセス
        for word in segment.words:
            for i, char in enumerate(word.word):
                char_info = CharInfo(
                    char=char,
                    start=word.start,
                    end=word.end,
                    # ... 他のフィールド
                )
                chars.append(char_info)
    else:
        # セグメントレベルでの処理
        pass
    
    return chars
```

### 3. キャッシュ形式の統一

現在のキャッシュはレガシー形式のJSONです。これを：
1. 新しいキャッシュは全てドメインエンティティ形式で保存
2. 既存キャッシュ読み込み時は自動変換
3. バージョン管理でスムーズな移行

```python
class TranscriptionCache:
    CURRENT_VERSION = "2.0"
    
    def save(self, result: TranscriptionResult, path: Path):
        """ドメインエンティティ形式で保存"""
        data = {
            "version": self.CURRENT_VERSION,
            "result": result.to_dict()
        }
        # ...
    
    def load(self, path: Path) -> TranscriptionResult:
        """バージョンに応じて適切に読み込み"""
        data = json.load(path)
        version = data.get("version", "1.0")
        
        if version == "1.0":
            # レガシー形式から変換
            legacy = LegacyTranscriptionResult.from_dict(data)
            return TranscriptionConverter.from_legacy(legacy)
        else:
            # ドメインエンティティ形式
            return TranscriptionResult.from_dict(data["result"])
```

## 期待される効果

1. **型安全性の向上**: 実行時エラーの大幅削減
2. **保守性の向上**: 明確なデータ構造により理解しやすく
3. **テストの簡素化**: モックが簡単に
4. **パフォーマンス向上**: 不要な変換処理の削除
5. **新機能追加の容易さ**: クリーンなアーキテクチャ

## リスクと対策

1. **既存キャッシュとの互換性**
   - 対策: 自動変換機能により透過的に処理

2. **大規模な変更によるバグ**
   - 対策: 段階的移行とテストカバレッジ向上

3. **一時的なパフォーマンス低下**
   - 対策: 変換処理の最適化

## タイムライン

- **Day 1**: TranscriptionConverterの実装とテスト
- **Day 2**: ゲートウェイ層の移行
- **Day 3**: ビジネスロジックの移行
- **Day 4**: UI層の移行とテスト
- **Day 5**: レガシーコードの削除と最終テスト