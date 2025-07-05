# Phase 3: ユースケース層実装計画

## 概要
ユースケース層はビジネスロジックのフローを定義し、ドメイン層と外部システム（インフラ層）を結びつけます。既存のcoreモジュールの機能を維持しながら、クリーンアーキテクチャの原則に従って再構成します。

## 実装方針

### 1. 既存ロジックの保護
- 既存のcoreモジュールはそのまま残す
- ゲートウェイインターフェースを通じて呼び出す
- 段階的な移行を可能にする

### 2. ユースケースの設計原則
- 単一責任の原則（1ユースケース = 1ビジネスフロー）
- 依存性逆転の原則（インターフェースに依存）
- テスタビリティ（モック可能な設計）

### 3. エラーハンドリング
- ユースケース固有の例外を定義
- 既存のエラーをラップして一貫性を保つ

## ユースケース一覧

### 文字起こし系
1. **TranscribeVideoUseCase**
   - 動画の文字起こしを実行
   - キャッシュチェック → 文字起こし → 保存

2. **LoadTranscriptionCacheUseCase**
   - キャッシュから文字起こし結果を読み込み
   - 複数のキャッシュから最新を選択

3. **ParallelTranscribeUseCase**
   - 大きな動画を並列で文字起こし
   - チャンク分割 → 並列実行 → 結果統合

### 編集系
4. **FindTextDifferencesUseCase**
   - テキストの差分を検出
   - 正規化 → 差分計算 → 時間範囲特定

5. **AdjustBoundariesUseCase**
   - 境界調整マーカーを適用
   - マーカー解析 → 時間範囲調整

### 動画処理系
6. **DetectSilenceUseCase**
   - 無音部分を検出
   - WAV抽出 → 無音検出 → セグメント計算

7. **ExtractVideoSegmentsUseCase**
   - 指定範囲の動画を抽出
   - 時間範囲 → 動画切り出し → 結合

### エクスポート系
8. **ExportFCPXMLUseCase**
   - Final Cut Pro用XMLを生成
   - セグメント → FCPXML生成 → ファイル保存

9. **ExportPremiereXMLUseCase**
   - Premiere Pro用XMLを生成
   - セグメント → XMEML生成 → ファイル保存

10. **ExportSRTUseCase**
    - SRT字幕を生成
    - セグメント → SRT生成 → ファイル保存

## 実装順序

### Step 1: 基本構造の作成（1日目）
1. ユースケース基底クラス
2. ゲートウェイインターフェース定義
3. 例外クラス定義

### Step 2: 文字起こしユースケース（2-3日目）
1. ITranscriptionGateway インターフェース
2. TranscribeVideoUseCase 実装
3. LoadTranscriptionCacheUseCase 実装
4. テスト作成

### Step 3: 編集ユースケース（4日目）
1. ITextProcessorGateway インターフェース
2. FindTextDifferencesUseCase 実装
3. AdjustBoundariesUseCase 実装
4. テスト作成

### Step 4: 動画処理ユースケース（5-6日目）
1. IVideoProcessorGateway インターフェース
2. DetectSilenceUseCase 実装
3. ExtractVideoSegmentsUseCase 実装
4. テスト作成

### Step 5: エクスポートユースケース（7-8日目）
1. IExportGateway インターフェース
2. 各エクスポートユースケース実装
3. テスト作成

### Step 6: 統合とリファクタリング（9-10日目）
1. ユースケース間の連携確認
2. パフォーマンステスト
3. ドキュメント更新

## ゲートウェイインターフェース設計

### ITranscriptionGateway
```python
from typing import Protocol, Optional
from domain.entities import TranscriptionResult
from domain.value_objects import FilePath

class ITranscriptionGateway(Protocol):
    """文字起こしゲートウェイ"""
    
    def transcribe(
        self,
        video_path: FilePath,
        model_size: str,
        language: Optional[str] = None,
        use_cache: bool = True
    ) -> TranscriptionResult:
        """動画を文字起こし"""
        ...
    
    def load_from_cache(
        self,
        video_path: FilePath,
        model_size: str
    ) -> Optional[TranscriptionResult]:
        """キャッシュから読み込み"""
        ...
    
    def save_to_cache(
        self,
        video_path: FilePath,
        model_size: str,
        result: TranscriptionResult
    ) -> None:
        """キャッシュに保存"""
        ...
```

### IVideoProcessorGateway
```python
from typing import Protocol, List, Tuple
from domain.value_objects import FilePath, TimeRange

class IVideoProcessorGateway(Protocol):
    """動画処理ゲートウェイ"""
    
    def extract_audio_segments(
        self,
        video_path: FilePath,
        time_ranges: List[TimeRange]
    ) -> List[FilePath]:
        """音声セグメントを抽出"""
        ...
    
    def detect_silence(
        self,
        audio_path: FilePath,
        threshold: float = -35,
        min_duration: float = 0.3
    ) -> List[TimeRange]:
        """無音を検出"""
        ...
    
    def combine_segments(
        self,
        video_path: FilePath,
        time_ranges: List[TimeRange],
        output_path: FilePath
    ) -> None:
        """セグメントを結合"""
        ...
```

## リスク管理

### 技術的リスク
1. **既存機能の破壊**
   - 対策: 既存coreモジュールは変更しない
   - 対策: 包括的な統合テスト

2. **パフォーマンス低下**
   - 対策: 抽象化のオーバーヘッドを最小化
   - 対策: ベンチマークテストの実施

3. **複雑性の増加**
   - 対策: シンプルなインターフェース設計
   - 対策: 明確なドキュメント

### 実装上の注意点
1. **キャッシュ機能の保持**
   - 既存のキャッシュ形式を維持
   - パフォーマンスを劣化させない

2. **並列処理の維持**
   - 既存の並列処理ロジックを活用
   - スレッドセーフな設計

3. **エラーハンドリング**
   - 既存の例外をそのまま活用
   - ユースケース層で適切にラップ

## 検証計画

### 単体テスト
- 各ユースケースに対してモックを使用したテスト
- 境界値テスト、異常系テスト

### 統合テスト
- 実際のcoreモジュールを使用した統合テスト
- パフォーマンステスト（処理時間の比較）

### 受け入れテスト
- 既存の機能が正しく動作することを確認
- UIからの動作確認

## 成功基準
1. すべての既存機能が正常に動作する
2. テストカバレッジ90%以上
3. パフォーマンスの劣化が5%以内
4. コードの可読性と保守性の向上