# TextffCut - 使用方法

## 概要
TextffCutは動画の文字起こしと切り抜きを効率化するツールです。
90分程度の長時間動画から必要な部分だけを抽出し、無音部分を自動削除してタイトな編集素材を作成できます。

## 必要なもの
- Docker（インストール済みであること）
- 2GB以上の空き容量

## インストール方法

### 1. ファイルの展開
配布されたファイルを展開すると以下が含まれています：
- `textffcut.tar` - Dockerイメージ
- `start.sh` - Mac/Linux用起動スクリプト
- `start.bat` - Windows用起動スクリプト
- `TextffCut使用方法.md` - このファイル

### 2. Dockerイメージの読み込み
```bash
# tarファイルがあるディレクトリで実行
docker load < textffcut.tar

# または、フルパスを指定
docker load < /path/to/textffcut.tar
```

### 3. 起動スクリプトに実行権限を付与（Mac/Linuxのみ）
```bash
chmod +x start.sh
```

### 4. 動作確認
```bash
docker images
```
`textffcut:latest`が表示されれば成功です。

## 使用方法

### 1. 作業フォルダの準備
```bash
# 作業フォルダを作成
mkdir textffcut-work
cd textffcut-work

# 必要なフォルダを作成
mkdir videos transcriptions
```

### 2. 動画ファイルの配置
処理したい動画ファイルを `videos/` フォルダにコピーまたは移動してください。

### 3. アプリケーションの起動

#### 方法1: 起動スクリプトを使用（推奨）
```bash
# Mac/Linux
./start.sh

# Windows
start.bat
```

#### 方法2: 手動でDockerコマンドを実行
```bash
# 作業フォルダ内でコマンド実行
docker run -p 8501:8501 \
  -v $(pwd)/videos:/app/videos \
  -v $(pwd)/transcriptions:/app/transcriptions \
  textffcut:latest
```

### 4. ブラウザでアクセス
http://localhost:8501 にアクセス

### 5. 基本的な使い方
1. **動画ファイル選択**: ドロップダウンから動画を選択
2. **文字起こし**: Whisperモデル（large-v3推奨）で文字起こし実行
3. **テキスト編集**: 残したい部分のテキストを編集
4. **エクスポート**: FCPXML形式で出力（`videos/`フォルダに保存）

## フォルダ構成
```
textffcut-work/     # 作業フォルダ（任意の名前）
├── videos/         # 動画ファイルの配置＆出力場所
└── transcriptions/ # 文字起こし結果
```

**注意**: 
- 入力動画と出力ファイル（FCPXML等）は同じ`videos/`フォルダに保存されます
- 出力ファイルは「元のファイル名_no_fillers」等の名前で保存されます

## 主な機能
- ✅ WhisperXによる高精度文字起こし
- ✅ 無音部分の自動検出・削除
- ✅ PAD設定（前後のパディング調整）
- ✅ Final Cut Pro / DaVinci Resolve対応のFCPXML出力

## トラブルシューティング

### ポートが使用済みの場合
```bash
# 別のポートを使用
docker run -p 8502:8501 \
  -v $(pwd)/videos:/app/videos \
  -v $(pwd)/transcriptions:/app/transcriptions \
  textffcut:latest
# → http://localhost:8502 でアクセス
```

### 権限エラーの場合
```bash
# 権限を付与
chmod 755 videos transcriptions
```

### 動画が表示されない場合
- `videos/`フォルダに動画ファイル（.mp4/.mov/.avi）が配置されているか確認
- ファイル名に特殊文字が含まれている場合は、英数字のファイル名に変更

## 停止方法
```bash
# Ctrl+C で停止
# または別ターミナルで
docker ps  # コンテナIDを確認
docker stop <コンテナID>
```

## サポート
質問やバグ報告があれば連絡してください。

## よくある質問

**Q: 複数の動画を処理したい場合は？**
A: 動画ごとに処理してください。出力ファイルは別名で保存されるので、同じフォルダで連続処理可能です。

**Q: 対応している動画形式は？**
A: .mp4、.mov、.avi形式に対応しています。

**Q: 処理時間はどのくらい？**
A: 90分動画で約5-10分（無音検出含む）です。

---
TextffCut v1.01 (シンプル版)