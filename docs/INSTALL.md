# TextffCut インストールガイド

TextffCutのインストール方法を説明します。

## 📋 必要な環境

### システム要件
- **OS**: macOS 10.15以降
- **メモリ**: 8GB以上推奨（16GB以上推奨）
- **ストレージ**: 10GB以上の空き容量

### ソフトウェア要件
- Python 3.8以降
- Homebrew（macOSパッケージマネージャー）
- FFmpeg（動画処理）

## 🚀 インストール方法

### 方法1: 自動インストール（推奨）

```bash
# 1. リポジトリをクローン
git clone https://github.com/Coidemo/TextffCut.git
cd TextffCut

# 2. インストールスクリプトを実行
./install.sh

# 3. 起動
./run.sh
```

### 方法2: 手動インストール

#### 1. 必要なソフトウェアのインストール

```bash
# Homebrewのインストール（未インストールの場合）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# FFmpegのインストール
brew install ffmpeg
```

#### 2. Pythonセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/Coidemo/TextffCut.git
cd TextffCut

# 仮想環境の作成
python3 -m venv venv

# 仮想環境の有効化
source venv/bin/activate

# pipのアップグレード
pip install --upgrade pip

# 依存関係のインストール
pip install -r requirements.txt
```

#### 3. 起動

```bash
# 仮想環境が有効な状態で
streamlit run main.py
```

### 方法3: Docker版

Docker Desktopがインストールされている場合：

```bash
# 1. リポジトリをクローン
git clone https://github.com/Coidemo/TextffCut.git
cd TextffCut

# 2. Docker版を起動
./docker-run.sh start

# 3. ブラウザで http://localhost:8501 にアクセス
```

## 🔧 インストール確認

### 環境診断ツール

```bash
# 環境の確認
python setup.py
```

このツールで以下を確認できます：
- macOSバージョン
- Pythonバージョン
- Homebrew/FFmpegの有無
- Apple Silicon対応状況

### 手動確認

```bash
# Pythonバージョン
python3 --version

# FFmpeg
ffmpeg -version

# PyTorch（Apple Silicon）
python3 -c "import torch; print(f'MPS: {torch.backends.mps.is_available()}')"
```

## ❓ トラブルシューティング

### よくある問題

#### 1. 「command not found: brew」エラー
Homebrewがインストールされていません。上記の手順でインストールしてください。

#### 2. 「No module named 'whisperx'」エラー
依存関係が正しくインストールされていません：
```bash
pip install -r requirements.txt
```

#### 3. FFmpegエラー
```bash
brew install ffmpeg
# または
brew reinstall ffmpeg
```

#### 4. メモリ不足エラー
- 他のアプリケーションを終了
- より小さいWhisperモデル（base, small）を使用

### Apple Silicon (M1/M2/M3) の場合

自動的にMetal Performance Shadersが使用されますが、問題がある場合：

```bash
# PyTorchの再インストール
pip uninstall torch torchaudio
pip install torch torchaudio
```

## 📝 インストール後の設定

### APIモードの設定（オプション）

OpenAI APIを使用する場合：

1. [OpenAI Platform](https://platform.openai.com/)でAPIキーを取得
2. アプリ起動後、サイドバーでAPIキーを設定
3. 「APIモードを使用」をチェック

### 推奨設定

- **Whisperモデル**: `large-v3`（高精度）または`medium`（バランス）
- **無音閾値**: -35dB（デフォルト）
- **最小無音時間**: 0.3秒

## 🆘 サポート

インストールで問題が発生した場合：

1. `setup.py`で環境診断を実行
2. エラーメッセージを確認
3. [Issues](https://github.com/Coidemo/TextffCut/issues)で報告

報告時に含めてほしい情報：
- macOSバージョン
- Pythonバージョン
- エラーメッセージ全文
- `setup.py`の出力結果