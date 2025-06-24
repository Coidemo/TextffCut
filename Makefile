# TextffCut Makefile
# AI自律開発支援用コマンド集

.PHONY: help lint format test test-fast check pre-commit validate-api debug-transcription clean

# デフォルトターゲット
help:
	@echo "TextffCut 開発コマンド:"
	@echo "  make lint          - コードのLintチェック（ruff, mypy）"
	@echo "  make format        - コードの自動フォーマット（black, ruff）"
	@echo "  make test          - 全テストを実行"
	@echo "  make test-fast     - 高速テストのみ実行"
	@echo "  make check         - format + lint + test を実行"
	@echo "  make pre-commit    - コミット前の全チェック"
	@echo "  make validate-api  - API定義の検証"
	@echo "  make debug-transcription - 文字起こしのデバッグ実行"
	@echo "  make clean         - キャッシュファイルをクリーンアップ"

# Lintチェック
lint:
	@echo "🔍 Lintチェックを実行中..."
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check .; \
	else \
		echo "⚠️  ruffがインストールされていません。flake8で代替実行..."; \
		flake8 . --exclude=.venv,venv,__pycache__,.mypy_cache,.pytest_cache,build,dist; \
	fi
	@echo "🔍 型チェックを実行中..."
	@if command -v mypy >/dev/null 2>&1; then \
		mypy . --config-file pyproject.toml; \
	else \
		echo "⚠️  mypyがインストールされていません"; \
	fi

# コードフォーマット
format:
	@echo "✨ コードフォーマットを実行中..."
	@if command -v black >/dev/null 2>&1; then \
		black .; \
	else \
		echo "⚠️  blackがインストールされていません"; \
	fi
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check --fix .; \
	else \
		echo "⚠️  ruffがインストールされていません"; \
	fi

# テスト実行
test:
	@echo "🧪 全テストを実行中..."
	@if command -v pytest >/dev/null 2>&1; then \
		pytest -v; \
	else \
		echo "❌ pytestがインストールされていません"; \
		exit 1; \
	fi

# 高速テスト（slowマーカーがないテストのみ）
test-fast:
	@echo "⚡ 高速テストを実行中..."
	@if command -v pytest >/dev/null 2>&1; then \
		pytest -v -m "not slow"; \
	else \
		echo "❌ pytestがインストールされていません"; \
		exit 1; \
	fi

# 全チェック実行
check: format lint test
	@echo "✅ 全チェック完了！"

# コミット前チェック
pre-commit: check
	@echo "✅ コミット前チェック完了！安全にコミットできます。"

# API定義の検証
validate-api:
	@echo "🔍 API定義を検証中..."
	@if [ -f scripts/validate_api_schema.py ]; then \
		python scripts/validate_api_schema.py; \
	else \
		echo "⚠️  API検証スクリプトが見つかりません"; \
		echo "📝 docs/api_schemas/ディレクトリのJSONファイルを確認..."; \
		find docs/api_schemas -name "*.json" -exec python -m json.tool {} \; > /dev/null && echo "✅ JSONフォーマット検証OK" || echo "❌ JSONフォーマットエラー"; \
	fi

# 文字起こしデバッグ
debug-transcription:
	@echo "🐛 文字起こしデバッグモードで実行中..."
	@if [ -f debug_transcription.py ]; then \
		python debug_transcription.py; \
	else \
		echo "📝 簡易デバッグ実行..."; \
		python -c "from core.transcription import Transcriber; print('✅ Transcriber import OK')"; \
		python -c "from config import Config; c = Config(); print(f'✅ Config loaded: API={c.transcription.use_api}')"; \
	fi

# クリーンアップ
clean:
	@echo "🧹 キャッシュファイルをクリーンアップ中..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "✅ クリーンアップ完了！"

# インストール確認
check-tools:
	@echo "🔧 開発ツールの確認..."
	@command -v python >/dev/null 2>&1 && echo "✅ Python: $$(python --version)" || echo "❌ Python not found"
	@command -v pip >/dev/null 2>&1 && echo "✅ pip: $$(pip --version | cut -d' ' -f2)" || echo "❌ pip not found"
	@command -v black >/dev/null 2>&1 && echo "✅ black: installed" || echo "⚠️  black not installed"
	@command -v ruff >/dev/null 2>&1 && echo "✅ ruff: installed" || echo "⚠️  ruff not installed"
	@command -v mypy >/dev/null 2>&1 && echo "✅ mypy: installed" || echo "⚠️  mypy not installed"
	@command -v pytest >/dev/null 2>&1 && echo "✅ pytest: installed" || echo "⚠️  pytest not installed"