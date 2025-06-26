# TextffCut E2Eテスト

## 概要
TextffCutの全機能を網羅的にテストするEnd-to-Endテストスイートです。
ブラウザを自動操作して、実際のユーザー操作をシミュレートします。

## ディレクトリ構造
```
tests/
├── e2e/                    # E2Eテスト
│   ├── test_full_workflow.py   # フルワークフローテスト
│   └── browser_base.py         # ブラウザ操作基底クラス
├── functional/             # 機能別テスト（今後追加）
├── config/                # テスト設定
│   └── test_config.yaml       # テスト設定ファイル
├── test_data/             # テストデータ
│   └── create_test_video.py   # テスト動画作成スクリプト
├── screenshots/           # スクリーンショット保存先
├── reports/              # テストレポート保存先
└── run_e2e_test.py      # テスト実行スクリプト
```

## セットアップ

### 1. テスト動画の作成
```bash
cd tests/test_data
python create_test_video.py
```

### 2. 環境変数の設定（APIテストを実行する場合）
```bash
export OPENAI_API_KEY="sk-..."
```

### 3. Streamlitアプリの起動
```bash
# プロジェクトルートで実行
streamlit run main.py
```

## テスト実行

### 基本的な実行
```bash
cd tests
python run_e2e_test.py
```

### 特定のテストのみ実行
設定ファイル（`config/test_config.yaml`）で、実行するテストを選択できます：

```yaml
test_suites:
  basic_ui: true           # 基本的なUI表示
  video_selection: true    # 動画選択機能
  transcription_api: false # API文字起こし（スキップ）
  transcription_local: true # ローカル文字起こし
  # ...
```

## テスト内容

### 1. 基本UI表示テスト
- タイトル・サブタイトルの表示
- サイドバーの表示
- 各タブの存在確認

### 2. 動画選択テスト
- Docker環境：ドロップダウンからの選択
- ローカル環境：パス入力フィールド
- 動画情報の表示

### 3. 文字起こしテスト
- APIモード（要APIキー）
  - モード選択
  - 料金表示
  - 処理実行
- ローカルモード
  - mediumモデル固定の確認
  - 処理実行

### 4. テキスト編集テスト
- 編集エリアの表示
- 差分表示（緑ハイライト）
- エラー検出（赤ハイライト）
- 区切り文字対応

### 5. エクスポートテスト
- FCPXMLファイル出力
- Premiere Pro XML出力
- 動画ファイル出力（MP4）
- 無音削除オプション

### 6. 設定機能テスト
- APIキー設定
- 無音検出パラメータ
- ヘルプ表示

## スクリーンショット
各テストステップでスクリーンショットが自動的に保存されます：
- `screenshots/YYYYMMDD_HHMMSS/` フォルダに保存
- 番号付きファイル名（例：`01_home.png`）
- エラー時のスクリーンショットも保存

## テストレポート
テスト完了後、JSONフォーマットでレポートが生成されます：
- `reports/e2e_report_YYYYMMDD_HHMMSS.json`
- テスト結果のサマリー
- 各テストの詳細
- スクリーンショットへのパス

## トラブルシューティング

### Streamlitアプリが起動していない
```
❌ エラー: Streamlitアプリが起動していません
```
→ `streamlit run main.py` でアプリを起動してください

### APIキーが設定されていない
```
⚠️ 注意: OPENAI_API_KEYが設定されていません
```
→ APIテストはスキップされます。実行する場合は環境変数を設定してください

### FFmpegがインストールされていない
```
❌ エラー: FFmpegがインストールされていません
```
→ テスト動画作成に必要です。各OSでインストールしてください：
- Mac: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`
- Windows: https://ffmpeg.org/download.html

## Puppeteer統合（実装例）

実際のブラウザ操作にはPuppeteer MCPを使用します。
以下は実装例です：

```python
# Puppeteerでナビゲート
await puppeteer_navigate(url=self.base_url)

# スクリーンショット撮影
await puppeteer_screenshot(
    name=filename,
    width=1280,
    height=720
)

# 要素のクリック
await puppeteer_click(selector="button[type='primary']")

# テキスト入力
await puppeteer_fill(
    selector="textarea",
    value="テスト文字列"
)
```

## 今後の拡張

1. **CI/CD統合**
   - GitHub Actionsでの自動実行
   - Dockerコンテナでのテスト

2. **パフォーマンステスト**
   - 処理時間の計測
   - メモリ使用量の監視

3. **負荷テスト**
   - 大きな動画ファイル
   - 長時間の処理

4. **回帰テスト**
   - バージョン間の動作比較
   - APIレスポンスの検証