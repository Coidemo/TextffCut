# 🎙️ TextffCut

動画の文字起こしと切り抜きを効率化するツール

**TextffCut** = Text + diff + Cut（テキスト差分による動画切り抜き）

## 🏷️ バージョン情報

- **v1.0.0-stable** (2024-05-28): 安定版リリース
  - 効率的なWAVベース無音検出
  - 90分動画対応
  - FCPXMLエクスポート最適化
  - 字幕機能を削除してシンプル化

## 概要

TextffCutは、YouTube等の動画から高精度な文字起こしを行い、必要な部分だけを切り抜いて編集ソフトで使えるファイルとして出力するツールです。

### 主な機能

- **高精度な文字起こし**: WhisperXを使用した日本語対応の文字起こし
- **直感的な切り抜き編集**: テキストベースで切り抜き箇所を選択
- **無音削除**: 切り抜いた動画から無音部分を自動削除
- **多様な出力形式**: 
  - 動画ファイル（MP4）
  - FCPXMLファイル（Final Cut Pro/DaVinci Resolve用）
- **設定の永続化**: よく使う設定を自動保存

## インストール

### 方法1: Docker（推奨）

**最も簡単で確実な方法です**

```bash
# リポジトリのクローン
git clone https://github.com/yourusername/textffcut.git
cd textffcut

# Docker Composeで起動
docker-compose up -d

# ブラウザで http://localhost:8501 にアクセス
```

### 方法2: ローカル環境

#### 必要な環境
- Python 3.8以上
- FFmpeg（動画処理用）

#### セットアップ
```bash
# リポジトリのクローン
git clone https://github.com/yourusername/textffcut.git
cd textffcut

# 依存関係のインストール
pip install -r requirements.txt
```

## 使い方

### 起動

#### Docker版
```bash
docker-compose up -d
# ブラウザで http://localhost:8501 にアクセス
```

#### ローカル版
```bash
streamlit run main.py
```

### 基本的な使用手順

1. **動画ファイルの準備**
   - Docker版: `videos/` フォルダに動画ファイルを配置
   - ローカル版: 動画ファイルのフルパスを入力

2. **文字起こし**
   - Whisperモデルを選択（large-v3推奨）
   - 「新しく文字起こしを実行」をクリック

3. **切り抜き箇所の指定**
   - 左側の文字起こし結果から必要な部分をコピー
   - 右側のテキストエリアにペースト
   - 「更新」ボタンで確定

4. **処理オプションの選択**
   - 処理タイプ：「切り抜きのみ」または「無音削除付き」
   - 出力形式：「動画ファイル」または「FCPXMLファイル」

5. **処理実行**
   - 「処理を実行」ボタンをクリック
   - 出力ファイルは `output/` フォルダに保存

### Docker版での注意事項

- **動画ファイル**: `videos/` フォルダに配置
- **出力ファイル**: `output/` フォルダに保存される
- **文字起こし結果**: `transcriptions/` フォルダに保存される
- **停止**: `docker-compose down` で停止

## プロジェクト構造

```
textffcut/
├── main.py              # メインアプリケーション
├── config.py            # 設定管理
├── core/                # コア機能
│   ├── transcription.py # 文字起こし処理
│   ├── text_processor.py # テキスト処理
│   ├── video.py         # 動画処理
│   └── export.py        # エクスポート処理
├── ui/                  # UI関連
│   ├── components.py    # UIコンポーネント
│   └── file_upload.py   # ファイル入力
└── utils/               # ユーティリティ
    ├── file_utils.py    # ファイル操作
    ├── settings.py      # 設定の保存/読み込み
    └── logging.py       # ロギング
```

## 今後の計画

- [ ] YouTube URL直接入力対応
- [ ] AIによる自動切り抜き候補提案
- [ ] EDL/OTIO形式のエクスポート対応
- [ ] バッチ処理機能
- [ ] Web API化

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 貢献

プルリクエストを歓迎します。大きな変更を行う場合は、まずissueを開いて変更内容について議論してください。