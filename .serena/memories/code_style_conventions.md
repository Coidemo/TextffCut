# コードスタイルとコンベンション

## Python設定
- **Python 3.11**: ターゲットバージョン
- **行長**: 120文字まで
- **文字エンコーディング**: UTF-8

## フォーマッター
- **Black**: 自動フォーマット（line-length=120）
- **isort**: import文の整理（profile=black）

## Linter設定
- **Ruff**: 高速Linter
  - pycodestyle (E, W)
  - pyflakes (F)
  - isort (I)
  - flake8-bugbear (B)
  - flake8-comprehensions (C4)
  - pyupgrade (UP)
  - flake8-annotations (ANN) - 型ヒント

## 型チェック
- **mypy**: 段階的な型チェック
  - coreとservicesモジュールは型チェック強化中
  - サードパーティライブラリはimport無視設定

## コーディング規約
- **型ヒント**: 新規コードには積極的に使用
- **docstring**: 重要な関数・クラスには記述
- **ログ**: loggingモジュール使用（logger変数）
- **エラーハンドリング**: core/error_handling.pyの専用クラス使用

## ファイル命名
- **Pythonファイル**: snake_case.py
- **クラス**: PascalCase
- **関数・変数**: snake_case
- **定数**: UPPER_SNAKE_CASE

## 除外パターン
- テストファイル（test_*.py）は型アノテーション不要
- 設定ファイル（config.py, setup.py）も型アノテーション不要