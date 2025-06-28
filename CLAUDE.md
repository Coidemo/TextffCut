# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🌐 言語設定
**会話は日本語で行ってください。**

## 🎯 プロジェクト概要

**TextffCut** - 動画の文字起こしと切り抜きを効率化するツール

主な用途：
- 90分程度の長時間動画から必要な部分だけを抽出
- 無音部分を自動削除してタイトな編集素材を作成
- DaVinci ResolveやFinal Cut Pro用のFCPXMLを生成

## 📌 安定版情報 (重要)

### v0.9.6 (2025-06-09) ⭐ **最新安定版**
- **タグ**: `v0.9.6`
- **コミット**: `b5c1ce1`
- **リモート**: GitHubにプッシュ済み

#### 主な特徴
- ✅ Docker Desktop割り当てメモリの80%を自動計算して使用
- ✅ メモリ管理の最適化（PC物理メモリではなくDocker割り当てベース）
- ✅ 大容量メモリ環境（128GB等）でも適切にスケール
- ✅ 効率的なWAVベース無音検出（90分動画対応）
- ✅ FCPXMLエクスポート最適化（隙間を詰めて配置）
- ✅ 時間範囲ベースの統一的な処理フロー

#### 新機能 (v0.9.6)
- **メモリ自動最適化**: Docker Desktop割り当てメモリを基準に適切な設定
- **スケーラビリティ**: 大規模環境でも安定動作
- **柔軟性向上**: reservations設定を削除し、より動的な動作を実現

### v1.01 (2025-05-30)
- **タグ**: `v1.01`
- **リモート**: GitHubにプッシュ済み

#### 主な特徴
- ✅ 無音削除時のPAD設定機能（セグメント前後のパディング調整）
- ✅ UI改善（ボタン配置最適化、レイアウト統一）
- ✅ 効率的なWAVベース無音検出（90分動画対応）
- ✅ FCPXMLエクスポート最適化（隙間を詰めて配置）
- ✅ 時間範囲ベースの統一的な処理フロー

### v1.0.0-stable (2024-05-28)
- **タグ**: `v1.0.0-stable`
- **ブランチ**: `stable-v1.0.0`
- **リモート**: GitHubにプッシュ済み

#### 主な特徴
- ✅ 効率的なWAVベース無音検出（90分動画対応）
- ✅ FCPXMLエクスポート最適化（隙間を詰めて配置）
- ✅ 字幕機能を削除してシンプル化
- ✅ 時間範囲ベースの統一的な処理フロー

#### 安定版に戻る方法
```bash
# 最新安定版に戻る（推奨）
git checkout v0.9.6

# 前バージョンの安定版に戻る
git checkout v1.01

# 旧安定版に戻る
git checkout v1.0.0-stable

# 最新の開発版に戻る
git checkout main
```

## 🏗️ 主要アーキテクチャ

プロジェクトはモジュール化されたアーキテクチャを採用：

```
buzz-clip/
├── main.py              # メインアプリケーション（Streamlit）
├── config.py            # 設定管理
├── core/                # コア機能
│   ├── transcription.py # WhisperXによる文字起こし
│   ├── text_processor.py # テキスト差分検出
│   ├── video.py         # 動画処理・無音検出
│   └── export.py        # FCPXML/EDLエクスポート
├── ui/                  # UI関連
│   ├── components.py    # Streamlitコンポーネント
│   └── file_upload.py   # ファイル入力処理（Docker/ローカル統一）
└── utils/               # ユーティリティ
```

### 環境統一仕様

Docker環境とローカル環境で完全に同一の動作を実現：

- **ファイル選択**: 両環境でvideosフォルダからドロップダウン選択
- **出力先**: 入力ファイルと同じvideosフォルダ
- **UI/UX**: 完全に同一（環境による表示の違いなし）
- **フォルダ自動作成**: videosフォルダが存在しない場合は自動的に作成

環境判定は内部的に行われ、ユーザーには意識させない設計：

```python
# 環境判定（内部処理）
is_docker = os.path.exists('/.dockerenv')

# パス解決（自動）
if is_docker:
    videos_dir = "/app/videos"
else:
    videos_dir = "./videos"
```

**統一された動作：**
1. 両環境で同じドロップダウン選択UI
2. videosフォルダの自動作成
3. フルパス（絶対パス）表示で明確な場所を提示

## 🔧 技術的な詳細

### 新しい処理フロー (v1.0.0以降)
1. **テキストから対象部分を特定**
   - `text_processor.find_differences()` で差分計算
   - 時間範囲（time_ranges）を取得

2. **無音検出（無音削除付きの場合）**
   - 対象範囲のWAVファイルを抽出 (`extract_audio_for_ranges`)
   - WAVから無音を検出 (`detect_silence_from_wav`)
   - 残す範囲（keep_ranges）を計算

3. **出力**
   - FCPXML: 時間範囲を直接記述（動画処理なし）
   - 動画: 必要部分のみ抽出して結合

### 重要なメソッド
- `VideoProcessor.remove_silence_new()`: 新しい効率的な無音検出
- `VideoProcessor.extract_audio_for_ranges()`: 複数範囲のWAV抽出
- `FCPXMLExporter.export()`: 正しいアセット参照でFCPXML生成

### 無音検出パラメータ
- **閾値**: -35dB（デフォルト）
- **最小無音時間**: 0.3秒
- **最小セグメント時間**: 0.3秒

## ⚠️ 注意事項

1. **FCPXMLのアセット参照**
   - 同じ動画は1つのアセット（例: r1）として定義
   - 全クリップが同じアセットを参照すること
   - 古いバージョンでは各クリップが別アセットになっていた（バグ）

2. **WAVファイルの管理**
   - 一時WAVファイルは `temp_wav/` に作成
   - 処理後に自動クリーンアップ

3. **時間計算の精度**
   - フレーム単位での丸めによる0.1秒程度の誤差は正常
   - FFmpegの `-ss` と `-to` オプションで正確な切り出し

4. **SRT字幕の仕様**
   - 字幕は文字起こしで得たタイムスタンプに基づいて生成
   - クリップ数と字幕数の一致は不要（独立して管理）
   - 重要な制約：字幕全体が動画全体の時間範囲内に収まること
   - 無音削除時は時間マッピングで字幕位置を調整

## 🌐 新機能: Whisper API統合（v1.1.0-dev）

### API/ローカル自動切り替え機能
- ✅ 統合Transcriberクラス（`core/transcription.py`）
- ✅ API版文字起こし（`core/transcription_api.py`）
- ✅ UI統合（API設定パネル）
- ✅ 環境変数による設定切り替え

#### サポートAPI
1. **OpenAI Whisper API**: 公式API、$0.006/分（専用最適化）

#### Streamlit Cloud用構成
- 依存関係: `requirements_streamlit_cloud.txt`
- 環境変数: `.env.example`参照
- API専用モード（WhisperXなし）

#### 使用方法
```bash
# ローカル版（従来通り）
streamlit run main.py

# API版（環境変数で切り替え）
TEXTFFCUT_USE_API=true TEXTFFCUT_API_KEY=sk-xxx streamlit run main.py

# または.envファイルで設定
echo "TEXTFFCUT_USE_API=true" > .env
echo "TEXTFFCUT_API_KEY=your_key" >> .env
streamlit run main.py
```

## 🔧 カスタムコンポーネント開発の学び

### Streamlitカスタムコンポーネントの重要な注意点

1. **ディレクトリ名の衝突を避ける**
   - `components.py`ファイルと`components/`ディレクトリが同じ階層にあるとインポートエラーが発生
   - 解決策：ディレクトリ名を`custom_components/`などに変更

2. **コンポーネントの基本構造**
   ```
   custom_components/
   └── timeline/
       ├── __init__.py      # Python wrapper
       └── frontend/
           └── index.html   # HTMLとJavaScriptを含む単一ファイル
   ```

3. **index.htmlの必須要素**
   - Streamlitライブラリの読み込み：`<script src="https://unpkg.com/streamlit-component-lib@1/dist/streamlit-component-lib.js"></script>`
   - `window.Streamlit.onRender()`でデータを受信
   - `window.Streamlit.setComponentReady()`で準備完了を通知
   - `window.Streamlit.setComponentValue()`でPythonにデータを送信

4. **デバッグのヒント**
   - コンポーネントが読み込まれない場合は、`_RELEASE`フラグを確認
   - パスが正しいことを確認（`path=`パラメータ）
   - ブラウザのコンソールでJavaScriptエラーを確認
   
5. **重要な学び（2025-06-26）**
   - Streamlitのカスタムコンポーネントは`npm run build`でビルドが必要な場合がある
   - シンプルな実装には`components.html()`を使う静的コンポーネントが有効
   - "Your app is having trouble loading the component"エラーは、フロントエンドアセットへのアクセス問題を示す
   - **JavaScriptからStreamlitへのデータ送信は、テキストエリアを介して行うのが確実**
   - **時間調整後は必ず`updateTextArea()`を呼び出して変更を反映する**

## 📊 タイムライン編集機能の実装状況

### 実装済み機能（2025-06-26）
1. **第1段階：基本機能** ✅
   - Canvas上に波形付きクリップ表示
   - クリック選択機能
   - 編集完了で処理セクションへ移行

2. **第2段階：境界調整機能** ✅
   - 数値入力による精密な時間調整（ミリ秒単位）
   - ボタンによる調整（±1秒、±0.1秒）
   - 入力検証（開始/終了時間の妥当性チェック）
   - リアルタイムでのテキストエリア更新

### 実装上の重要ポイント
1. **タイムライン編集の任意実行**
   - 更新ボタンでは`show_timeline_section`を自動設定しない
   - 「タイムライン編集」ボタンでユーザーが明示的に開始
   - 編集済みの場合は「✅ タイムライン編集済み」と表示

2. **編集結果の反映**
   - JavaScriptで`updateTextArea()`を呼び出し
   - JSON形式で時間範囲をテキストエリアに保存
   - 「編集完了」ボタンで`adjusted_time_ranges`に反映

3. **波形表示の課題**
   - 現在、時間調整しても波形自体は変わらない（波形データの再取得が必要）
   - 将来的には動的な波形更新を検討

### トラブルシューティング

1. **タイムライン編集が反映されない場合**
   - 「編集完了」ボタンを押す前に、編集結果（JSON）のテキストエリアに変更が反映されているか確認
   - JavaScriptコンソールでエラーがないか確認
   - 処理実行時に「📊 タイムライン編集済みの時間範囲を使用します」が表示されるか確認

2. **デバッグモード**
   - 処理実行時に`st.write`でデバッグ情報を表示（ただしspinner内では表示されない）
   - `adjusted_time_ranges`がセッション状態に保存されているか確認

## 💼 開発運用ルール

### 開発作業の進め方（AI向け指示）

新機能開発や変更作業を行う際は、既存ドキュメントを活用した段階的アプローチに従うこと：

#### 1. 要件確認フェーズ
ユーザーから機能要望があった場合：
- まず `/docs/requirements_definition.md` を確認
- 要望が既存要件と矛盾する場合は必ず確認：
  「この要望は要件定義書の〇〇と矛盾しますが、要件定義を変更しますか？」
- 要件定義書は原則変更しない（ユーザー承認がある場合のみ）

#### 2. 設計更新フェーズ
要件に沿った開発の場合：
- **変更前に必ず確認**：「基本設計書と詳細設計書に以下の変更を加えてよろしいですか？」
  - 変更箇所の説明
  - 変更理由
  - 影響範囲
- ユーザー承認後に `/docs/basic_design_specification_v2.md` を更新
- 続いて `/docs/detailed_design_specification_v3.md` を更新

#### 3. タスク分解フェーズ
設計確定後：
- 「以下のタスクに分解して実装を進めてよろしいですか？」と確認
- タスクリストを提示
- 承認後にTodoWriteツールで登録

#### 4. 実装フェーズ
- 詳細設計書に従って実装
- 実装中に設計変更が必要になった場合：
  1. 作業を一旦停止
  2. 「実装中に〇〇の問題が判明しました。設計を以下のように変更してよろしいですか？」
  3. 承認後に設計書を更新してから実装再開

#### 具体例
```
ユーザー: モデルを自由に選択できるようにしたい
AI: 要件定義書では「中程度の精度モデルを使用（固定）」となっています。
    この要件を変更してモデル選択機能を追加しますか？

[ユーザーが要件変更を選択]

AI: 承知しました。それでは以下の変更を行ってよろしいですか？
    
    1. 要件定義書：
       - 「中程度の精度モデルを使用」→「複数モデルから選択可能」
    
    2. 基本設計書：
       - モデル選択UIの追加
       - 設定保存機能の追加
    
    3. 詳細設計書：
       - config.pyにmodel_size設定追加
       - UIにドロップダウン追加
    
    この方針で進めてよろしいですか？
```

#### 重要な原則
- **何かを変更する前に必ず確認を取る**
- 要件定義書 → 基本設計書 → 詳細設計書の階層を守る
- 実装は詳細設計書の承認後に開始
- 想定外の問題が発生したら、独断で進めず相談

### ブランチ戦略
1. **新機能開発は必ず新しいブランチで作業する**
   ```bash
   # 新機能用ブランチを作成
   git checkout -b feature/機能名
   # 例: git checkout -b feature/youtube-url-support
   ```

2. **開発完了後の流れ**
   - ユーザーからOKが出るまでブランチで作業
   - OKが出たらプルリクエストを作成
   - mainブランチにマージ

3. **ブランチ命名規則**
   - `feature/機能名`: 新機能
   - `fix/バグ名`: バグ修正
   - `refactor/対象`: リファクタリング

### コミットメッセージ
- 日本語でOK
- プレフィックスを使用: `feat:`, `fix:`, `docs:`, `refactor:`

## 🚀 今後の開発方針

### 優先度高
- [ ] YouTube URL直接入力対応
- [ ] AIによる自動切り抜き候補提案

## 📝 開発時のコマンド

```bash
# アプリケーション起動
streamlit run main.py

# インポート確認
python -c "from main import main; print('Import OK')"

# 無音検出のテスト
python -c "from core.video import VideoProcessor; print('Video OK')"

# FCPXMLのテスト生成
python -c "from core.export import FCPXMLExporter; print('Export OK')"
```

### 自己検証の実施

#### コード品質チェック
実装後、以下のコマンドを必ず実行：
```bash
make check  # フォーマット、Lint、テストを一括実行
```

問題がある場合は自己修正を試みる。修正できない場合はユーザーに相談。

#### API/外部リソースの確認
外部APIを使用する前に：
1. `/docs/api_schemas/`で仕様を確認
2. 不明な点は`make validate-api`で検証
3. 新しいAPIは必ずスキーマを文書化

#### デバッグ支援
問題が発生した場合：
- `make debug-transcription` - 文字起こしのデバッグ
- `pytest -v -k "test_name"` - 特定テストの実行
- ログファイルは`logs/`ディレクトリを確認

#### 実装時の確認事項
1. **コミット前チェック**
   ```bash
   make pre-commit  # 必ず実行
   ```
2. **データ構造の参照**
   - `/docs/data_structures.md`で正確な型定義を確認
   - 特にWordInfo、CharInfoは辞書形式であることに注意
3. **エラーハンドリング**
   - `core/error_handling.py`の既存エラークラスを使用
   - 新しいエラーパターンは必ず`ErrorCategory`に分類

## 🔄 定期メンテナンスタスク

### API料金情報の更新確認
**頻度**: 月1回（毎月第1週）  
**担当**: 開発者  
**タスク**:
1. [OpenAI Pricing](https://openai.com/pricing)でWhisper API料金を確認
2. 現在のコード内料金情報と比較
3. 変更があれば以下を更新：
   - `main.py:137行目`: API料金（$0.006/分）
   - `main.py:155行目`: 料金記載日付
   - `README_API.md`: 料金シミュレーション部分
4. 大幅な料金変更があればユーザーに通知

**チェックポイント**:
- Whisper API料金: 現在 $0.006/分（2025年5月時点）
- 料金変更履歴をGitコミットで記録
- 円換算レート（150円/USD）も適宜見直し

**関連ファイル**:
- `/main.py` (料金確認ダイアログ)
- `/README_API.md` (料金説明)
- `/ui/components.py` (料金表示)

## 📦 配布パッケージ作成

### 配布パッケージ作成（正式な方法）
購入者向けのパッケージを作成するには：

```bash
# Docker版の配布用パッケージを作成（メモリ最適化版）
./build_release.sh [バージョン番号]
# 例: ./build_release.sh 0.9.6
# バージョン番号を省略すると最新のGitタグを使用
```

これにより `release/TextffCut_v[バージョン].zip` が作成されます。

**パッケージ内容:**
- Dockerイメージ（tar.gz形式、約750MB）
- 起動スクリプト（START.command/bat）- メモリ自動最適化機能付き
- docker-compose-simple.yml
- README.txt

**配布前の確認事項:**
1. Docker Desktopでパッケージの動作確認
2. Mac/Windows両方での起動確認

### 使用しないスクリプト（廃止予定）
以下のスクリプトは古い形式のため使用しません：
- `scripts/create_release_package.sh` - 古い形式（アンインストール機能など）
- `scripts/create_docker_release.sh` - 別の形式
- `scripts/create_release.sh` - 用途不明

## 🎉 最近の改善（2025-06-26）

### ✅ タイムライン編集機能の実装完了！
最終的に**シンプルで確実な実装**（`timeline_editor_simple.py`）で解決：
- Streamlitネイティブの`number_input`で各クリップを個別編集
- JavaScriptとの複雑な連携を完全に排除
- 編集した値が確実に`adjusted_time_ranges`に保存され、出力に反映される
- 「10秒に調整したら、ちゃんと10秒で出力される」ことを確認

## 🎉 最近の改善（2025-06-26）

### タイムライン編集の問題修正
1. **編集結果が出力に反映されない問題の調査**
   - 症状：10秒に調整したのに、出力は元の6秒のまま
   - 原因：JavaScriptからStreamlitへのデータ転送の根本的な問題
   - 修正過程：
     - `updateTextArea()`関数にデバッグログを追加
     - 初期化時にもテキストエリアを更新するよう修正
     - 編集完了ボタン押下時にデバッグ情報を表示
     - インポートエラーを修正（timeline_editor → timeline_editor_static）

2. **デバッグ機能の追加**
   - 編集されたJSONデータの可視化（デバッグ情報エクスパンダー）
   - 初期値と現在値の比較表示
   - JavaScriptコンソールログの追加
   - 処理実行時の時間範囲デバッグ表示

3. **重要な発見と最終解決策**
   - `components.html()`で作成した静的コンポーネント内のJavaScriptは、DOMContentLoadedイベント後に実行される
   - **JavaScriptでDOM操作してもStreamlitのセッション状態は自動更新されない（根本的な制限）**
   - **最終解決策：`timeline_editor_simple.py`を作成**
     - Streamlitネイティブの`number_input`を使用
     - JavaScriptとの複雑な連携を完全に排除
     - 各クリップに対して直接数値入力で編集
     - 確実に動作することを優先

### タイムライン編集機能の実装
1. **インタラクティブなタイムライン編集UI**
   - Canvas上に波形付きクリップを表示
   - クリックでクリップを選択
   - 数値入力とボタンで境界を精密に調整（ミリ秒単位）
   - 静的HTMLコンポーネント（`components.html()`）で実装

2. **任意タイミングでの編集**
   - 更新ボタンでは自動表示されない
   - 「📊 タイムライン編集」ボタンで明示的に開始
   - 編集済みの場合は「✅ タイムライン編集済み」と表示

3. **JavaScript-Streamlit連携**
   - `updateTextArea()`で編集結果を自動的にJSON形式で保存
   - テキストエリアを介したデータ送信で確実な連携

### 実装上の重要な学び
- Streamlitのカスタムコンポーネントは`npm run build`が必要な場合がある
- 静的コンポーネント（`components.html()`）の方がシンプルで確実
- JavaScriptからの値の受け渡しはテキストエリアを使うのが安定
- `components.py`と`components/`ディレクトリの名前衝突に注意

## 🎉 最近の改善（2025-06-25）

### SRT字幕エクスポートの最適化
1. **無音削除時の自然な字幕分割**
   - 無音削除により分割されたセグメントを、ユーザー設定（文字数×行数）内で賢く結合
   - 例：「6月5日の木曜日かな」「木曜日」「はい8時でございます」→ 2エントリに結合

2. **改行位置の最適化**
   - 1行目でmax_line_lengthまで使い切るように改善
   - 「6月5日の木曜日かな／木曜日」のように自然な位置で改行

3. **TimeMapperの拡張**
   - `map_range_to_segments`メソッドで範囲分割を検出
   - 単一の時間範囲が複数セグメントに分割される場合を正確に追跡

## 🐛 既知の問題

1. **メモリ使用量**: 2GB以上の動画ファイルで問題になる可能性
2. **Windows対応**: FFmpegパスの設定が必要な場合がある
3. **古いブランチ**: `refactor/module-split`は不完全（使用しない）

## 📊 パフォーマンス指標

- 90分動画の処理: 約5-10分（無音検出含む）
- WAV抽出: 10秒あたり約1秒
- 無音検出: リアルタイムの約2倍速
- FCPXML生成: 即座（<1秒）

## 🔧 進行中の作業 (2025-06-28)

### main.pyリファクタリング（正しいアプローチ）

#### 背景
- main.pyが2072行に膨れ上がり、保守性が低下
- 前回のリファクタリング試行で機能を変更してしまう失敗
- 今回は**機能・コードを一切変えず、ファイル分割のみ**を実施

#### リファクタリング方針
1. **絶対に変更しないもの**
   - 機能・動作
   - コードの内容（一字一句同じ）
   - 画面遷移・UI/UX
   
2. **変更してよいもの**
   - ファイルの場所
   - import文の追加のみ

3. **作業手順**
   - 各関数・定数を一つずつ移動
   - 移動前後でdiffを取り、完全一致を確認
   - 動作確認を都度実施
   - 定期的にCLAUDE.mdを更新して/compactを実行

#### 現在の進捗
- ブランチ: `feature/refactor-main`
- 状態: main.pyを元の2072行に戻し、正しいリファクタリングを開始
- 開始時刻: 2025-06-28 19:53

##### 作業状況
1. **目的確認** ✅ 機能・コードを一切変えず、main.pyを分割するだけ
2. **次の作業**: `get_display_path`関数の移動
   - 移動元: main.py
   - 移動先: utils/file_utils.py
   - 予定: 関数コードの完全コピー、使用箇所の特定、import追加

#### 移動予定の項目
1. **ユーティリティ関数**
   - `get_display_path` → `utils/file_utils.py`
   - `debug_words_status` → `utils/logging.py`

2. **定数**
   - `PROCESSING_STATES` → `core/constants.py`（存在確認必要）
   - UI関連定数 → `ui/constants.py`（新規作成）

3. **大きな処理ブロック**（main.py内で関数化後、必要に応じて移動）
   - 文字起こし処理
   - テキスト編集処理
   - 処理実行部分
   - サイドバー処理

#### 重要な注意事項
- 定期的に目的を再確認：「機能・コードを一切変えず、分割するだけ」
- 各ステップでコンテキストを保持（CLAUDE.md更新、/compact実行）
- 移動前後のコードが完全一致することを必ず確認

---

最終更新: 2025-06-28
次回開発時はこのファイルを必ず確認してください。
特に安定版（v0.9.6）の情報は重要です。