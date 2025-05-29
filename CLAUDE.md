# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🌐 言語設定
**会話は日本語で行ってください。**

## 🎯 プロジェクト概要

**Buzz Clip** - 動画の文字起こしと切り抜きを効率化するツール

主な用途：
- 90分程度の長時間動画から必要な部分だけを抽出
- 無音部分を自動削除してタイトな編集素材を作成
- DaVinci ResolveやFinal Cut Pro用のFCPXMLを生成

## 📌 安定版情報 (重要)

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
│   └── file_upload.py   # ファイル入力処理
└── utils/               # ユーティリティ
```

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

## 🐛 既知の問題

1. **メモリ使用量**: 2GB以上の動画ファイルで問題になる可能性
2. **Windows対応**: FFmpegパスの設定が必要な場合がある
3. **古いブランチ**: `refactor/module-split`は不完全（使用しない）

## 📊 パフォーマンス指標

- 90分動画の処理: 約5-10分（無音検出含む）
- WAV抽出: 10秒あたり約1秒
- 無音検出: リアルタイムの約2倍速
- FCPXML生成: 即座（<1秒）

---

最終更新: 2024-05-28
次回開発時はこのファイルを必ず確認してください。
特に安定版（v1.0.0-stable）の情報は重要です。