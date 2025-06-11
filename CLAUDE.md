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

### v0.9.7-beta (2025-06-11) 🆕 **ベータ版**
- **タグ**: `v0.9.7-beta`
- **ブランチ**: `fix/0.9.6-bugfix-clean`

#### 主な変更点
- ✅ Whisper mediumモデル固定（高速・高精度）
- ✅ モデルをDockerイメージに事前同梱
- ✅ Windowsでのアライメントモデルダウンロード問題を解決
- ✅ オフライン環境でも確実に動作
- ✅ UIからモデル選択を削除（シンプル化）

#### 技術的詳細
- パッケージサイズ: 約2GB（Dockerイメージ: 13.1GB）
- Whisper mediumモデル: 1.5GB
- 日本語アライメントモデル同梱
- 90分動画の処理: 5-10分（環境依存）

### v1.01 (2025-05-30) ⭐ **最新安定版**
- **タグ**: `v1.01`
- **リモート**: GitHubにプッシュ済み

#### 主な特徴
- ✅ 無音削除時のPAD設定機能（セグメント前後のパディング調整）
- ✅ UI改善（ボタン配置最適化、レイアウト統一）
- ✅ 効率的なWAVベース無音検出（90分動画対応）
- ✅ FCPXMLエクスポート最適化（隙間を詰めて配置）
- ✅ 時間範囲ベースの統一的な処理フロー

#### 新機能 (v1.01)
- **PAD設定**: セグメント開始前・終了後のパディング時間（0-0.5秒）を調整可能
- **自然なつなぎ**: 音の急激な切り替わりを緩和して聞きやすい動画に
- **UI最適化**: 文字起こしボタンの配置・色調整、レイアウト統一

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
│   └── file_upload.py   # ファイル入力処理（Docker/ローカル分岐）
└── utils/               # ユーティリティ
```

### Docker版とローカル版の分岐

環境判定は `/.dockerenv` ファイルの存在で自動的に行われます：

```python
import os
is_docker = os.path.exists('/.dockerenv')
```

**主な分岐箇所：**

1. **動画ファイル入力** (`ui/file_upload.py`)
   - Docker版：`/app/videos/`内の動画をドロップダウンで選択
   - ローカル版：フルパス入力

2. **出力先設定**
   - Docker版：`/app/videos/`固定（入力と同じ場所）
   - ローカル版：動画と同じフォルダの`output/`またはカスタム指定

3. **UIメッセージ**
   - Docker版：「videos/フォルダ内の動画ファイルを選択してください」
   - ローカル版：「動画ファイルのフルパス」

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

## 💼 開発運用ルール

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
- [ ] バッチ処理機能
- [ ] プリセット機能（よく使う設定の保存）

### 優先度中
- [ ] EDL/OTIO形式のエクスポート
- [ ] AIによる自動切り抜き候補提案
- [ ] Web API化

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

## 🐛 既知の問題

1. **メモリ使用量**: 2GB以上の動画ファイルで問題になる可能性
2. **Windows対応**: FFmpegパスの設定が必要な場合がある
3. **古いブランチ**: `refactor/module-split`は不完全（使用しない）

## 📊 パフォーマンス指標

- 90分動画の処理: 約5-10分（無音検出含む）
- WAV抽出: 10秒あたり約1秒
- 無音検出: リアルタイムの約2倍速
- FCPXML生成: 即座（<1秒）

## 🚀 PyInstaller移行プロジェクト (2025-06-11開始)

### 開発状況
- **現在のフェーズ**: Phase 1 - MVP版
- **ブランチ**: `feature/pyinstaller-build`
- **目的**: Windows/Mac両対応のスタンドアロンアプリ化

### 段階的実装計画

#### Phase 1: MVP版（実装中）
- [x] 最小限のStreamlit UI（`textffcut_mvp.py`）
- [x] 動画ファイル選択機能
- [x] 動画情報表示（時間、サイズ等）
- [x] PyInstallerでのビルド確認
- **サイズ**: 341MB（最適化前）
- **課題**: Streamlitの起動方法の調整が必要

**進捗メモ (2025-06-12):**
- MVP版のUIを作成完了
- PyInstallerでビルド成功（コンソール版/GUI版）
- 実行時にStreamlitの起動に課題あり
- ランチャースクリプト（`textffcut_mvp_launcher.py`）を作成

#### Phase 2: 動画処理版（実装中）
- [x] 音声抽出（WAV）- `textffcut_video.py`
- [x] 動画情報取得（ffprobe使用）
- [ ] 無音検出
- [ ] 簡易カット機能
- **サイズ**: 7.1MB（ffmpeg別途必要）

**進捗メモ (2025-06-12):**
- Video版作成（ffmpeg/ffprobe使用）
- 動画情報表示と音声抽出機能実装
- PyInstallerビルド成功（7.1MB）

#### Phase 3: API文字起こし版
- [ ] OpenAI Whisper API統合
- [ ] API設定UI
- [ ] 文字起こし結果表示
- **サイズ目標**: <300MB

#### Phase 4: フル機能版
- [ ] WhisperXローカル統合
- [ ] アライメント機能
- [ ] 完全なFCPXML出力
- **サイズ目標**: <1GB

### ビルド手順
```bash
# Mac版ビルド
pyinstaller textffcut_mvp.spec

# Windows版ビルド（Windows環境で実行）
pyinstaller textffcut_mvp_win.spec
```

### テスト済み環境
- macOS: 未テスト
- Windows: 未テスト

### トークン切れ対策
- 各フェーズ完了時にコミット
- 進捗はこのセクションに随時更新
- 問題発生時の詳細もここに記載

---

最終更新: 2025-06-11
次回開発時はこのファイルを必ず確認してください。
特に安定版（v0.9.6）の情報は重要です。