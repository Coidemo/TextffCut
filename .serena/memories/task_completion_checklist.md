# タスク完了時のチェックリスト

## 必須実行項目

### 1. コード品質チェック
```bash
make check  # または make pre-commit
```
これにより以下が実行されます：
- コードフォーマット（Black, Ruff）
- Lintチェック（Ruff, mypy）
- テスト実行（pytest）

### 2. 問題がある場合の対処
```bash
# フォーマットエラー
make format

# Lintエラー
make lint  # エラー内容を確認して修正

# テストエラー
pytest -v --tb=short  # 詳細なエラー情報を確認
```

### 3. コミット前の確認事項
- [ ] `make pre-commit` が成功することを確認
- [ ] 新規ファイルは.gitignoreに含まれていないか確認
- [ ] 機密情報（APIキー等）が含まれていないか確認
- [ ] CLAUDE.mdの指示に従っているか確認

### 4. 特定の状況での追加確認

#### 文字起こし機能を変更した場合
```bash
make debug-transcription
```

#### API定義を変更した場合
```bash
make validate-api
```

#### 大規模な変更の場合
```bash
# 全テストを実行
make test

# 型チェックを詳細に
mypy . --config-file pyproject.toml
```

### 5. Docker環境での確認
```bash
# Dockerで動作確認
docker-compose up -d
docker logs textffcut_app
```

### 6. ドキュメント更新
重要な変更があった場合：
- CLAUDE.mdの更新が必要か確認
- README.mdの更新が必要か確認

## 注意事項
- **コミット前に必ずmake pre-commitを実行**
- **テストが失敗する変更はコミットしない**
- **型エラーは段階的に修正（完璧を求めすぎない）**