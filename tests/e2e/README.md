# E2Eブラウザテスト

このディレクトリには、Playwrightを使用したブラウザ自動化E2Eテストが含まれています。

## 🚀 実行方法

### 1. 簡単な実行（推奨）

```bash
python tests/e2e/run_browser_tests.py
```

このスクリプトは自動的に：
- Playwrightをインストール
- 必要なブラウザ（Chromium）をダウンロード
- テストを実行
- スクリーンショットを保存

### 2. 手動実行

```bash
# Playwrightのインストール
pip install playwright
playwright install chromium

# テストの実行
pytest tests/e2e/test_text_editor_browser.py -v --browser chromium --headed
```

## 📸 スクリーンショット

テスト実行時のスクリーンショットは以下の場所に保存されます：

```
tests/e2e/screenshots/
└── YYYYMMDD_HHMMSS/  # タイムスタンプ付きディレクトリ
    ├── 01_initial_load_HHMMSS.png
    ├── 02_before_upload_HHMMSS.png
    ├── 03_video_selection_HHMMSS.png
    └── ...
```

## 🧪 テストシナリオ

1. **初期ページ読み込み** - アプリケーションが正しく起動することを確認
2. **動画アップロードフロー** - ファイル選択UIの表示確認
3. **文字起こしセクション** - 文字起こし機能のUI確認
4. **テキストエディタUI** - 編集機能と境界調整モードの確認
5. **レスポンシブレイアウト** - 異なる画面サイズでの表示確認
6. **エラー状態** - エラーメッセージの表示確認
7. **完全なワークフロー** - 全セクションの統合的な動作確認

## ⚙️ 設定

### ブラウザオプション

- **ヘッドレスモード**: `--headed`フラグで実際のブラウザを表示
- **ブラウザ選択**: `--browser chromium/firefox/webkit`
- **スローモーション**: デバッグ時は`--slowmo 1000`で動作を遅く

### タイムアウト

- ページ読み込み: 30秒
- 要素の検出: 5秒（デフォルト）

## 🔍 デバッグ

失敗したテストのデバッグ：

```bash
# デバッグモードで実行
pytest tests/e2e/test_text_editor_browser.py -v --headed --slowmo 1000 -s

# 特定のテストのみ実行
pytest tests/e2e/test_text_editor_browser.py::TestTextEditorBrowserE2E::test_initial_page_load -v
```

## 📝 新しいテストの追加

1. `test_text_editor_browser.py`に新しいテストメソッドを追加
2. `save_screenshot()`メソッドで重要な状態をキャプチャ
3. `expect()`を使用してアサーションを追加

```python
def test_new_feature(self, page: Page, streamlit_server: str):
    """新機能のテスト"""
    page.goto(streamlit_server)
    page.wait_for_selector('[data-testid="stApp"]')
    
    # テストロジック
    feature_button = page.locator('text="新機能"')
    feature_button.click()
    
    # スクリーンショット
    self.save_screenshot(page, "new_feature_clicked")
    
    # アサーション
    expect(page.locator('.result')).to_be_visible()
```