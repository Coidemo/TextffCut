# 推奨コマンド一覧

## アプリケーション起動
```bash
# Dockerで起動（推奨）
./docker-compose-with-port-check.sh  # ポート自動検出付き
docker-compose up -d                  # 通常起動

# ローカルで起動
streamlit run main.py

# APIモードで起動
TEXTFFCUT_USE_API=true TEXTFFCUT_API_KEY=sk-xxx streamlit run main.py
```

## 開発コマンド
```bash
# コード品質チェック（必須）
make check         # format + lint + test 一括実行
make pre-commit    # コミット前の全チェック

# 個別実行
make format        # コードの自動フォーマット
make lint          # Lintチェック
make test          # 全テスト実行
make test-fast     # 高速テストのみ

# デバッグ
make debug-transcription  # 文字起こしのデバッグ
make check-tools         # 開発ツールの確認
```

## Git操作
```bash
# ブランチ作成（新機能開発時）
git checkout -b feature/機能名

# コミット（プレフィックス付き）
git commit -m "feat: 新機能の説明"
git commit -m "fix: バグ修正の説明"
git commit -m "docs: ドキュメント更新"
git commit -m "refactor: リファクタリング"

# 安定版に戻る
git checkout v0.9.6     # 最新安定版
git checkout main       # 開発版
```

## テスト実行
```bash
# 特定テストの実行
pytest -v -k "test_name"

# パスを指定して実行（例）
PYTHONPATH=/Users/naoki/myProject/TextffCut pytest tests/unit/domain/ -v

# カバレッジ付き実行
pytest --cov=core --cov-report=html
```

## Docker操作
```bash
# コンテナ確認
docker ps
docker logs textffcut_app

# クリーンアップ
docker-compose down
docker system prune -f
```

## システムコマンド（macOS）
```bash
# ファイル検索
find . -name "*.py" -type f
rg "検索文字列"  # ripgrep（高速検索）

# プロセス確認
ps aux | grep streamlit
lsof -i :8501  # ポート使用確認
```