# TextffCut 2段階処理アーキテクチャ 網羅的テスト計画

## 1. テスト戦略

### 1.1 テスト観点
1. **構文・インポートエラー**
   - Python構文エラー
   - インポートエラー
   - 循環参照

2. **実行時エラー**
   - インデックスエラー
   - 型エラー
   - None参照
   - 未定義変数

3. **統合性**
   - 新旧コードの連携
   - APIモード/ローカルモードの切り替え
   - 既存機能への影響

4. **未使用コード**
   - デッドコード
   - 未使用のインポート
   - 未使用の関数/クラス

5. **エッジケース**
   - 空のデータ処理
   - 例外処理
   - エラーリカバリ

6. **互換性**
   - 既存のキャッシュファイル
   - 旧形式のTranscriptionResult
   - V2形式への移行

## 2. テスト項目

### 2.1 静的解析テスト
- [ ] 全Pythonファイルの構文チェック
- [ ] インポート依存関係の確認
- [ ] 未使用コードの検出
- [ ] 型ヒントの整合性

### 2.2 単体テスト

#### データモデル (core/models.py)
- [ ] WordInfo: is_valid()メソッド
- [ ] TranscriptionSegmentV2: validate_for_search()
- [ ] TranscriptionSegmentV2: get_word_at_position()
- [ ] TranscriptionResultV2: validate_for_processing()
- [ ] TranscriptionResultV2: require_valid_words()
- [ ] 旧形式との変換: to_legacy_format()

#### 例外クラス (core/exceptions.py)
- [ ] WordsFieldMissingError: メッセージ生成
- [ ] AlignmentValidationError: 成功率計算
- [ ] SubprocessError: stderr処理
- [ ] get_user_message()の出力確認

#### インターフェース (core/interfaces.py)
- [ ] 抽象メソッドの定義確認
- [ ] 実装クラスとの整合性

#### 統一トランスクライバー (core/unified_transcriber.py)
- [ ] process()メソッドの基本フロー
- [ ] _process_transcription()
- [ ] _process_alignment()
- [ ] エラーハンドリング
- [ ] プログレス報告

#### アライメントプロセッサー (core/alignment_processor.py)
- [ ] align()メソッド
- [ ] align_single_segment()
- [ ] estimate_timestamps()
- [ ] _fix_word_continuity()

#### リトライハンドラー (core/retry_handler.py)
- [ ] should_retry()の判定ロジック
- [ ] get_delay()の計算
- [ ] AdaptiveRetryStrategy
- [ ] with_retryデコレーター

### 2.3 統合テスト

#### 既存コードとの連携
- [ ] transcription.py: validate_has_words()
- [ ] transcription.py: to_v2_format()
- [ ] main.py: 文字起こし結果の表示前検証
- [ ] worker_transcribe.py: transcribe_onlyモード
- [ ] worker_align.py: 新形式での処理

#### ワークフロー
- [ ] ローカルモード: 文字起こし→アライメント
- [ ] APIモード: API呼び出し→アライメント
- [ ] キャッシュ読み込み
- [ ] エラー時のリトライ

### 2.4 エッジケーステスト
- [ ] 空のセグメントリスト
- [ ] wordsフィールドが全てNone
- [ ] 部分的にwordsが欠落
- [ ] タイムスタンプの不整合
- [ ] 言語コードの不一致

### 2.5 パフォーマンステスト
- [ ] メモリ使用量の測定
- [ ] 処理時間の比較
- [ ] サブプロセスの起動/終了

## 3. テスト実行手順

### Phase 1: 静的解析
1. Pythonファイルの構文チェック
2. インポート依存関係の確認
3. 未使用コードの検出

### Phase 2: 基本動作確認
1. 新規ファイルのインポートテスト
2. 基本的なクラスのインスタンス化
3. メソッドの呼び出し

### Phase 3: 既存機能との統合
1. main.pyの起動確認
2. 文字起こし処理の実行
3. エラーメッセージの表示

### Phase 4: エッジケース
1. 異常データでの動作確認
2. エラーリカバリの確認

## 4. 成功基準
- 全ての構文エラーが解消されている
- インポートエラーが発生しない
- 既存機能が正常に動作する
- wordsフィールド欠落時に適切なエラーが表示される
- メモリリークが発生しない