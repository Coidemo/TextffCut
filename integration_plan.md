# 既存システムへの2段階処理アーキテクチャ統合計画

## 目標
新しい2段階処理アーキテクチャ（文字起こし→アライメント）を既存のmain.pyに統合し、wordsフィールドの必須化を実現する。

## 現状分析

### 既存システムの構造
1. **main.py** - Streamlitベースのメインアプリケーション
   - process_with_api() - API版文字起こし
   - process_with_local() - ローカル版文字起こし
   - render_transcription_section() - 文字起こし結果表示

2. **core/transcription.py** - 既存のTranscriberクラス
   - TranscriptionResult（V1形式）
   - to_v2_format()メソッドで変換

3. **core/transcription_api.py** - APITranscriberクラス

### 新アーキテクチャの構造
1. **core/unified_transcriber.py** - UnifiedTranscriber
2. **core/models.py** - TranscriptionResultV2、WordInfo
3. **core/alignment_processor.py** - AlignmentProcessor
4. **core/exceptions.py** - カスタム例外クラス

## 統合計画

### フェーズ1: 最小限の統合（リスク低）
1. **既存の処理フローを維持しつつ、検証を強化**
   - process_with_api/localの出力に対してwordsフィールド検証を追加
   - エラー時は新しい例外クラスでユーザーフレンドリーなメッセージ表示
   - 既存の動作を壊さない

2. **実装内容**
   - main.pyのrender_transcription_section()でrequire_valid_words()を呼び出す
   - エラーハンドリングの追加
   - UIに検証状態を表示

### フェーズ2: 部分的な統合（リスク中）
1. **APIモードで2段階処理を有効化**
   - APITranscriberの後にAlignmentProcessorを実行
   - プログレスバーの更新（文字起こし50%、アライメント50%）
   - ローカルモードは既存のまま

2. **実装内容**
   - process_with_api()でUnifiedTranscriberを使用
   - UIにアライメント進捗を表示
   - アライメント失敗時のリトライ機能

### フェーズ3: 完全統合（リスク高）
1. **全モードで2段階処理を使用**
   - ローカルモードもUnifiedTranscriberに移行
   - サブプロセス分離でメモリ効率化
   - キャッシュ機能の実装

2. **実装内容**
   - process_with_local()でUnifiedTranscriberを使用
   - worker_transcribe.py/worker_align.pyの活用
   - キャッシュマネージャーの統合

## リスクと対策

### リスク
1. **後方互換性の喪失**
   - 対策: 既存のTranscriptionResultを維持し、段階的に移行

2. **パフォーマンスの低下**
   - 対策: アライメント処理をオプション化

3. **UIの複雑化**
   - 対策: シンプルなプログレス表示から開始

### ロールバック計画
- 各フェーズごとにgitタグを作成
- 環境変数で新機能のON/OFFを制御
- 問題発生時は前のフェーズに戻る

## 実装優先順位

1. **最優先（フェーズ1）**
   - wordsフィールド検証の追加
   - エラーメッセージの改善
   - 既存機能への影響なし

2. **次優先（フェーズ2）**
   - APIモードでの2段階処理
   - プログレスバーの改良
   - アライメント結果の表示

3. **将来的に（フェーズ3）**
   - 完全な統合
   - メモリ最適化
   - キャッシュ機能

## 成功基準
1. wordsフィールドなしでは処理が停止する
2. エラー時にユーザーが対処法を理解できる
3. 既存の機能が正常に動作する
4. パフォーマンスが大幅に低下しない

## タイムライン
- フェーズ1: 1-2時間
- フェーズ2: 2-4時間
- フェーズ3: 4-8時間（別日程で実施）