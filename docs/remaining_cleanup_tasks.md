# 残作業リスト

## 1. レガシーUIコンポーネントの削除（優先度：高）

### servicesに依存しているファイル
新アーキテクチャで使用されていないことを確認済み：

- `ui/session_state_adapter.py` - servicesを使用
- `ui/timeline_editor.py` - servicesを使用（timeline_editor_simple.pyを使用中）
- `utils/config_helpers.py` - servicesを使用
- `utils/export_helpers.py` - servicesを使用

### 推奨アクション
これらのファイルは削除可能ですが、main_legacy.pyがまだ使用している可能性があるため、main_legacy.py削除時に一緒に削除することを推奨。

## 2. テストファイルの整理（優先度：中）

### ルートディレクトリのテストファイル
以下のファイルをtests/ディレクトリに移動または削除：

```
test_alignment_diagnostics.py
test_api_alignment_v097.py
test_api_audio_path.py
test_api_real_scenario.py
test_constants.py
test_error_handling.py
test_fix.py
test_gc_optimization_integration.py
test_main_import.py
test_memory_management_integration.py
test_mvp.py
test_mvp_app.py
test_mvp_flow.py
test_orchestrator_integration.py
test_parameter_fix.py
test_processing_state_manager.py
test_recovery_ui.py
test_refactoring_complete.py
test_refactoring_integration.py
test_service_error_handling.py
test_service_integration.py
test_smoke.py
test_srt_natural_breaks.py
test_srt_natural_split.py
test_srt_performance.py
test_state_recovery_integration.py
test_timeline_editing.py
test_type_hints.py
test_worker_align_integration.py
test_worker_direct.py
test_worker_integration.py
test_worker_refactored.py
test_worker_restart.py
```

## 3. 不要なログファイル（優先度：低）

### ルートディレクトリのログファイル
```
build.log
build_optimized.log
build_optimized_v2.log
build_optimized_v3.log
mvp_app.log
mvp_output.log
mvp_output2.log
mvp_output3.log
mvp_output4.log
mvp_output5.log
mvp_recent.log
recent_mvp.log
release_build.log
test_run.log
```

## 4. その他の不要ファイル（優先度：低）

### デバッグ・検証用ファイル
```
capture_error.py
check_mvp_errors.py
debug_error.py
debug_segments_type.py
fix_type_annotations.py
```

### 古いドキュメント
```
refactoring_*.md（複数ファイル）
phase2-2_test_report.md
```

## 5. infrastructure/uiディレクトリの確認

`infrastructure/ui/sections/export_section_legacy.py` がservicesを使用している。
新アーキテクチャでは使用されていないため、削除可能。

## 6. main_legacy.pyの削除（最終段階）

### 前提条件
1. 新アーキテクチャ（main.py）ですべての機能が動作確認済み
2. ユーザーへの事前通知
3. 適切な移行期間の確保

### 一緒に削除するファイル
- main_legacy.py
- servicesに依存するレガシーUIコンポーネント
- utils/config_helpers.py
- utils/export_helpers.py
- その他のレガシー専用ファイル

## まとめ

残作業の優先順位：

1. **高**: レガシーUIコンポーネントの特定（ただし、main_legacy.pyと一緒に削除を推奨）
2. **中**: テストファイルの整理（tests/ディレクトリへの移動）
3. **低**: ログファイルやデバッグファイルの削除
4. **最終**: main_legacy.pyとその依存ファイルの削除

新アーキテクチャは完全に独立して動作しているため、これらの削除作業は安全に実行できます。