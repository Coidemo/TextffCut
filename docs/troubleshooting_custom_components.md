# カスタムコンポーネントのトラブルシューティング

## 概要
Streamlitカスタムコンポーネント開発時に遭遇した問題と解決方法を記録します。

## 1. ディレクトリ名の競合問題

### 問題
- `ui/components.py`ファイルと`ui/components/`ディレクトリが共存していた
- Pythonは`from .components import`で**ディレクトリを優先**してインポートしようとする
- これにより`ImportError: cannot import name 'show_api_key_manager'`エラーが発生

### エラーメッセージ
```
ImportError: cannot import name 'show_api_key_manager' from 'components' 
(/Users/naoki/myProject/TextffCut/ui/components/__init__.py)
```

### 解決方法
ディレクトリ名を`components`から`custom_components`に変更：
```bash
mv ui/components ui/custom_components
```

インポート文を更新：
```python
# ui/timeline_editor.py
from .custom_components.timeline import timeline_editor
```

### 学習事項
- Pythonはモジュール名の解決時にディレクトリを優先する
- ファイルとディレクトリで同じ名前を使用することは避ける
- 明確で競合しない命名規則を採用する

## 2. カスタムコンポーネントのディレクトリ構造

### 推奨構造
```
ui/
├── components.py                    # レガシーコンポーネント
├── custom_components/              # カスタムコンポーネント用ディレクトリ
│   ├── __init__.py
│   └── timeline/                   # タイムラインエディタ
│       ├── __init__.py            # Pythonラッパー
│       └── frontend/              # フロントエンド
│           ├── index.html
│           ├── main.js
│           ├── package.json
│           └── build/             # ビルド成果物
│               ├── index.html
│               └── main.js
└── __init__.py
```

### ベストプラクティス
1. カスタムコンポーネントは専用ディレクトリに配置
2. レガシーコンポーネントとの名前競合を避ける
3. 各コンポーネントは独立したディレクトリとして管理
4. フロントエンドコードは`frontend/`サブディレクトリに配置
5. ビルド成果物は`build/`に配置

## 3. デバッグ方法

### Streamlitアプリのデバッグ
```bash
# ログファイルに出力
python -m streamlit run main.py > streamlit.log 2>&1

# ヘッドレスモードで実行
python -m streamlit run main.py --server.headless true
```

### ブラウザの確認（Puppeteer使用）
```python
# MCPツールを使用
mcp__puppeteer__puppeteer_navigate(url="http://localhost:8502")
mcp__puppeteer__puppeteer_screenshot(name="debug", width=1200, height=800)
```

### プロセスの確認
```bash
# Streamlitプロセスの確認
ps aux | grep streamlit

# ポートの確認
lsof -i :8502
```

## 4. インポートエラーの診断

### 問題の特定手順
1. エラーメッセージの確認
2. ディレクトリ構造の確認（`ls -la`）
3. `__init__.py`の内容確認
4. Pythonのモジュール検索パスの確認

### よくある原因
- 同名のディレクトリとファイルの競合
- 相対インポートの誤り
- 循環インポート
- `__init__.py`の不適切な設定

## 5. カスタムコンポーネントの開発フロー

### 初期設定
1. ディレクトリ構造の作成
2. `__init__.py`でコンポーネント関数の定義
3. フロントエンドコードの作成
4. ビルドディレクトリの準備

### 開発時の注意点
- `_RELEASE`フラグでデバッグモードと本番モードを切り替え
- フロントエンドの変更後は必ずビルドディレクトリにコピー
- Streamlitの再起動が必要な場合がある

### トラブルシューティングチェックリスト
- [ ] ディレクトリ名の競合はないか？
- [ ] インポートパスは正しいか？
- [ ] ビルドファイルは最新か？
- [ ] Streamlitは正常に起動しているか？
- [ ] ブラウザのコンソールにエラーはないか？

---

最終更新: 2025-01-26