# Phase 5: DI実装計画

## 実装方針

dependency-injectorを使用し、既存のコードベースと共存しながら段階的に移行する。

## 実装ステップ

### Step 1: 基盤構築（リスク: 低）

#### 1.1 dependency-injectorのインストール
```bash
pip install dependency-injector
```

#### 1.2 DIコンテナの基本構造
```
di/
├── __init__.py
├── containers.py      # メインコンテナ
├── providers.py       # カスタムプロバイダー
└── config.py         # DI用設定
```

#### 1.3 基本コンテナの作成
- ApplicationContainerクラス
- 設定プロバイダー
- ロギングプロバイダー

### Step 2: 設定管理の統合（リスク: 中）

#### 2.1 ConfigProviderの実装
- 既存のConfigクラスをラップ
- 環境変数との統合
- Streamlitセッション状態との同期機能

#### 2.2 設定の一元管理
- グローバルconfigへの参照を段階的に置き換え
- DIコンテナ経由での設定取得

### Step 3: ゲートウェイの登録（リスク: 低）

#### 3.1 アダプター層の登録
```python
# 登録するゲートウェイ
- FileGatewayAdapter
- TranscriptionGatewayAdapter
- TextProcessorGatewayAdapter
- VideoProcessorGatewayAdapter
- FCPXMLExportGatewayAdapter
- SRTExportGatewayAdapter
```

#### 3.2 ファクトリープロバイダーの作成
- 条件に応じたゲートウェイの選択
- API/ローカルの切り替え

### Step 4: ユースケースの登録（リスク: 低）

#### 4.1 ユースケースプロバイダー
```python
# 登録するユースケース
- TranscribeVideoUseCase
- ProcessTextDifferenceUseCase
- RemoveSilenceUseCase
- ExportProjectUseCase
- GenerateSubtitlesUseCase
```

#### 4.2 依存関係の自動解決
- ゲートウェイの自動注入
- 設定の自動注入

### Step 5: サービス層の移行（リスク: 中）

#### 5.1 既存サービスのラッピング
- ConfigurationService
- TranscriptionService
- VideoProcessingService
- TextEditingService

#### 5.2 サービスプロバイダーの作成
- シングルトンパターンの適用
- ライフサイクル管理

### Step 6: main.pyの段階的移行（リスク: 高）

#### 6.1 エントリーポイントの作成
```python
# di/bootstrap.py
def create_app():
    container = ApplicationContainer()
    container.wire(modules=[__name__])
    return container
```

#### 6.2 Streamlit統合
- st.session_stateとの連携
- 動的な設定変更への対応

#### 6.3 段階的な置き換え
1. 新機能から優先的にDI化
2. 重要度の低い機能から順次移行
3. コア機能は最後に移行

### Step 7: ワーカープロセスの対応（リスク: 高）

#### 7.1 ワーカー用コンテナ
- 軽量なコンテナの作成
- JSONシリアライズ可能な設定

#### 7.2 プロセス間通信
- 設定の受け渡し方法
- DIコンテナの再構築

### Step 8: テスト環境の整備（リスク: 低）

#### 8.1 テスト用コンテナ
- モックプロバイダーの設定
- テストごとのコンテナリセット

#### 8.2 統合テストの更新
- DIコンテナを使用したテスト
- 依存関係のモック化

## 実装の優先順位

### Phase 1（1週目）
1. ✅ 基盤構築（Step 1）
2. ✅ 設定管理の統合（Step 2）
3. ✅ 基本的なテスト

### Phase 2（2週目）
1. ✅ ゲートウェイの登録（Step 3）
2. ✅ ユースケースの登録（Step 4）
3. ✅ 統合テスト

### Phase 3（3週目）
1. ⏳ サービス層の移行（Step 5）
2. ⏳ main.pyの部分的移行（Step 6の一部）

### Phase 4（4週目）
1. ⏳ main.pyの完全移行（Step 6）
2. ⏳ ワーカープロセスの対応（Step 7）
3. ⏳ 全体テスト

## リスク管理

### 技術的リスク
1. **パフォーマンス低下**
   - 対策: プロファイリングツールで監視
   - 対策: 必要に応じて最適化

2. **循環依存**
   - 対策: 明確な層構造の維持
   - 対策: 依存関係グラフの可視化

3. **メモリ使用量増加**
   - 対策: プロバイダーのスコープ管理
   - 対策: 不要なインスタンスの解放

### 移行リスク
1. **既存機能の破壊**
   - 対策: 段階的移行
   - 対策: 十分なテスト
   - 対策: ロールバック計画

2. **開発速度の低下**
   - 対策: 十分なドキュメント
   - 対策: ペアプログラミング
   - 対策: サンプルコード

## 成功基準

1. **機能面**
   - 既存の全機能が正常に動作
   - テストカバレッジ80%以上

2. **パフォーマンス**
   - 起動時間の増加が1秒以内
   - メモリ使用量の増加が100MB以内

3. **保守性**
   - 新機能追加時の工数削減
   - テストの書きやすさ向上

## 移行後の構造

```
textffcut/
├── di/                        # DI関連
│   ├── __init__.py
│   ├── containers.py          # DIコンテナ定義
│   ├── providers.py           # カスタムプロバイダー
│   └── config.py             # DI設定
├── main.py                    # DIを使用
├── domain/                    # ビジネスロジック（変更なし）
├── use_cases/                 # ユースケース（変更なし）
├── adapters/                  # アダプター（変更なし）
└── core/                      # レガシーコード（段階的に削減）
```

## 次のアクション

1. dependency-injectorのインストール
2. di/ディレクトリの作成
3. 基本的なApplicationContainerの実装
4. 1つのゲートウェイで動作確認