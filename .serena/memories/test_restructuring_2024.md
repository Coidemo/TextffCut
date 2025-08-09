# テスト再構築記録 (2024年)

## 背景
- 既存のテストコードが古いAPIや存在しないモジュールを参照
- 649個のテストのうち多くがインポートエラー
- メンテナンスコストが高いため、全削除して一から作成することを決定

## 実施内容
1. `tests` ディレクトリを `tests_old_backup` にバックアップ
2. 新しいテスト構造を作成:
   ```
   tests/
   ├── __init__.py
   ├── conftest.py
   ├── unit/
   │   ├── core/
   │   ├── domain/
   │   └── utils/
   ├── integration/
   └── e2e/
   ```
3. conftest.pyでプロジェクトルートをPythonパスに追加
4. pytest.iniから`pythonpath = .`を削除（conftest.pyで対応）

## 注意事項
- 古いテストは`tests_old_backup`に保存されている
- 必要に応じて参照可能だが、直接使用は推奨しない