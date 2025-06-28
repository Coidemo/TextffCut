# main.py 詳細分析レポート

## 1. ファイル全体の構造

### 1.1 行数統計
- **総行数**: 2,073行
- **インポート部分**: 1-50行（50行）
- **CSS設定**: 51-143行（92行）
- **ヘルパー関数**: 144-185行（41行）
- **main関数**: 186-2,061行（1,875行）
- **エントリーポイント**: 2,066-2,073行（8行）

### 1.2 インポート分析

#### コアモジュール
```python
from core import TextProcessor
from core.alignment_processor import AlignmentProcessor
from core.constants import ApiSettings, ModelSettings
from core.error_handling import ErrorHandler
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription_subprocess import SubprocessTranscriber
```

#### サービス層
```python
from services import (
    ConfigurationService,
    ExportService,
    TextEditingService,
    VideoProcessingService
)
```

#### UI関連
```python
from ui import (
    apply_dark_mode_styles,
    cleanup_temp_files,
    show_api_key_manager,
    show_diff_viewer,
    show_export_settings,
    show_help,
    show_progress,
    show_red_highlight_modal,
    show_silence_settings,
    show_text_editor,
    show_transcription_controls,
    show_video_input,
)
from ui.recovery_components import (
    show_recovery_check,
    show_recovery_history,
    show_recovery_settings,
    show_recovery_status,
    show_startup_recovery,
)
```

#### ユーティリティ
```python
from utils import ProcessingContext, cleanup_intermediate_files
from utils.environment import IS_DOCKER, VIDEOS_DIR
from utils.file_utils import ensure_directory, get_safe_filename
from utils.logging import get_logger
from utils.time_utils import format_time
```

### 1.3 グローバル変数・定数
- `logger`: ロガーインスタンス（50行目）
- `icon_path`: アイコンパス設定（55-61行目）
- Streamlit設定（62-64行目）

## 2. main関数の詳細分析

### 2.1 主要セクション

#### (1) 初期設定・UI表示（186-248行）
- ロゴ・タイトル表示
- バージョン情報取得
- 起動時リカバリーチェック

#### (2) サイドバー設定（248-286行）
- APIキー管理
- 無音検出パラメータ
- SRT字幕設定
- リカバリー設定
- 処理履歴
- ヘルプ

#### (3) 動画入力処理（288-327行）
- 動画ファイル選択
- 動画パス変更検知
- セッション状態クリア

#### (4) 文字起こし処理（330-823行）
- **最大のセクション（493行）**
- リカバリーチェック
- 処理モード選択（API/ローカル）
- キャッシュ管理
- 文字起こし実行
- エラーハンドリング

#### (5) 切り抜き箇所指定（824-1350行）
- **2番目に大きいセクション（526行）**
- 文字起こし結果検証
- テキスト編集UI
- 差分表示
- 境界調整モード
- 音声プレビュー

#### (6) タイムライン編集（1351-1382行）
- オプショナルな編集機能
- シンプル版エディター使用

#### (7) 切り抜き処理実行（1383-2048行）
- **3番目に大きいセクション（665行）**
- 処理オプション設定
- 無音削除処理
- XML/動画出力
- SRT字幕生成
- プログレス表示

#### (8) モーダル・UI更新（2049-2061行）
- エラーモーダル表示
- UI再読み込み処理

### 2.2 行数分析（主要処理部分）

| セクション | 行番号範囲 | 行数 | 割合 |
|-----------|-----------|------|------|
| 文字起こし処理 | 330-823 | 493行 | 26.3% |
| 切り抜き箇所指定 | 824-1350 | 526行 | 28.0% |
| 切り抜き処理実行 | 1383-2048 | 665行 | 35.5% |
| その他 | - | 191行 | 10.2% |

## 3. リファクタリング候補の特定

### 3.1 文字起こし関連のコード

#### 主要箇所
- **文字起こし設定UI**: 412-499行（88行）
- **文字起こし実行**: 593-823行（230行）
- **アライメント処理**: 659-741行（82行）

#### 抽出可能な機能
1. 文字起こしモード選択UI
2. 料金計算・表示ロジック
3. キャッシュ管理ロジック
4. プログレス表示・キャンセル処理
5. アライメント処理フロー

### 3.2 テキスト編集関連のコード

#### 主要箇所
- **差分表示**: 886-944行（58行）
- **テキストエディタ**: 945-999行（54行）
- **更新ボタン処理**: 1011-1266行（255行）
- **境界調整モード**: 1016-1099行（83行）

#### 抽出可能な機能
1. テキスト差分計算・表示
2. 境界調整マーカー処理
3. エラーチェック（追加文字、マーカー位置）
4. 音声プレビュー生成

### 3.3 処理実行関連のコード

#### 主要箇所
- **無音削除処理**: 1549-1587行（38行）
- **XML出力**: 1590-1811行（221行）
- **動画出力**: 1813-2022行（209行）
- **SRT出力**: 複数箇所に分散

#### 抽出可能な機能
1. 処理タイプ判定ロジック
2. 出力ファイル名生成
3. プログレス管理
4. 中間ファイルクリーンアップ

### 3.4 共通処理・ユーティリティ

#### 識別された共通処理
1. **エラーハンドリングパターン**（複数箇所）
2. **セッション状態管理**（全体に分散）
3. **プログレス表示**（複数箇所）
4. **パス表示変換**（Docker/ローカル）

## 4. 依存関係の分析

### 4.1 使用サービス
- `ConfigurationService`: 設定管理、料金計算
- `ExportService`: XML/EDL出力
- `TextEditingService`: テキスト編集機能
- `VideoProcessingService`: 動画処理全般

### 4.2 UIコンポーネントの使用頻度
- `show_progress`: 13回
- `st.error`: 35回
- `st.info`: 8回
- `st.success`: 6回
- `st.spinner`: 2回

### 4.3 セッション状態の主要キー
```python
# 頻繁に使用されるキー
- transcription_result
- edited_text
- time_ranges
- adjusted_time_ranges
- use_api
- api_key
- show_timeline_section
- boundary_adjustment_mode
```

## 5. リファクタリング推奨事項

### 5.1 即時対応可能
1. **文字起こし設定UI**を独立関数に抽出（88行削減）
2. **エラーハンドリング**の共通化（約50行削減）
3. **プログレス管理**クラスの作成（約30行削減）

### 5.2 中期的対応
1. **文字起こし処理**全体を別モジュールに（493行）
2. **テキスト編集処理**を別モジュールに（526行）
3. **出力処理**を統合モジュールに（665行）

### 5.3 長期的対応
1. **ページ分割**：Streamlitのマルチページ機能を使用
2. **状態管理**：専用の状態管理クラスを作成
3. **処理フロー**：ワークフローエンジンの導入

## 6. 複雑度の高い箇所

### 6.1 条件分岐が多い箇所
- 更新ボタン処理（1011-1266行）：境界調整モードの有無で大きく分岐
- 処理実行（1431-2048行）：出力形式による分岐が複雑

### 6.2 ネストが深い箇所
- アライメント処理（659-741行）：try-except内に条件分岐
- SRT出力処理：複数箇所に同様のコードが分散

### 6.3 重複コードパターン
- SRT出力処理：4箇所で類似コード
- エラーハンドリング：同じパターンが10箇所以上
- パス表示変換：3箇所で同じロジック

## まとめ

main.pyは2,073行の大規模ファイルで、main関数だけで1,875行を占めています。主要な処理は以下の3つのセクションに集中しています：

1. **文字起こし処理**（26.3%）
2. **テキスト編集**（28.0%）
3. **処理実行**（35.5%）

これらのセクションを別モジュールに分割することで、約1,684行（全体の81%）を削減できる可能性があります。特に、共通処理の抽出と重複コードの削除により、即座に約170行の削減が可能です。