# 🎙️ TextffCut - Docker版

動画の文字起こしと切り抜きを効率化するツール（Docker版）

**TextffCut** = Text + diff + Cut（テキスト差分による動画切り抜き）

## 🚀 クイックスタート

### 必要な環境
- Docker Desktop（macOS/Windows/Linux対応）

### 起動方法

```bash
# 1. プロジェクトをダウンロード
git clone [このリポジトリのURL]
cd textffcut

# 2. Docker起動
docker-compose up -d

# 3. ブラウザでアクセス
open http://localhost:8501
```

## 📋 使用方法

### 1. 動画ファイルの指定
- **フルパス入力**: `/Users/username/Desktop/video.mp4`
- **対応形式**: MP4, MOV, AVI, MKV

### 2. 文字起こし
- **Whisperモデル**: large-v3推奨（高精度）
- **処理時間**: 90分動画で約5-10分

### 3. 切り抜き編集
- **テキストベース編集**: 必要な部分をコピー＆ペースト
- **無音削除**: 自動で無音部分を削除
- **PAD設定**: セグメント前後の調整（0-0.5秒）

### 4. 出力
- **保存先**: 動画と同じフォルダ
- **形式**: 動画ファイル（MP4）またはFCPXML

## 🔧 主な機能

### ✅ 高精度文字起こし
- WhisperXによる日本語対応
- GPUアクセラレーション対応（CUDA/MPS）

### ✅ 効率的な無音削除  
- WAVベース無音検出
- 90分動画対応
- 自然なつなぎ処理

### ✅ 編集ソフト連携
- Final Cut Pro対応（FCPXML）
- DaVinci Resolve対応（FCPXML）
- 隙間を詰めて配置

### ✅ 設定の永続化
- よく使う設定を自動保存
- 前回使用した動画パスを記憶

## 📁 出力ファイル例

```
/Users/username/Desktop/
├── original_video.mp4                    # 元動画
├── original_video_cut.mp4                # 切り抜き動画
├── original_video_no_silence.mp4         # 無音削除版
└── original_video.fcpxml                 # FCPXML
```

## ⚡ パフォーマンス

- **90分動画の処理**: 約5-10分
- **メモリ使用量**: 2-4GB
- **ストレージ**: 元動画の約50-80%

## 🛠️ トラブルシューティング

### Docker起動しない
```bash
# Docker Desktopが起動しているか確認
docker --version

# コンテナ再起動
docker-compose restart
```

### 動画が読み込めない
- パスに日本語・スペースが含まれていないか確認
- ファイル形式が対応しているか確認（MP4推奨）

### 処理が重い
- Whisperモデルを`base`または`medium`に変更
- 他のアプリケーションを終了してメモリを確保

## 📞 サポート

- **Issues**: バグ報告・機能要望
- **Discussions**: 使用方法の質問

---

**⚠️ 注意**: このソフトウェアは限定配布版です。第三者への再配布はご遠慮ください。