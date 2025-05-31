# TextffCut トラブルシューティングガイド

TextffCutで発生する可能性のある問題と解決方法をまとめています。

## 📋 目次

1. [インストール関連](#インストール関連)
2. [起動時の問題](#起動時の問題)
3. [文字起こしエラー](#文字起こしエラー)
4. [処理エラー](#処理エラー)
5. [出力関連](#出力関連)
6. [パフォーマンス問題](#パフォーマンス問題)
7. [API関連](#api関連)
8. [Docker関連](#docker関連)

## 🔧 インストール関連

### Homebrewが見つからない

**エラー**: `command not found: brew`

**解決方法**:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### FFmpegエラー

**エラー**: `ffmpeg: command not found`

**解決方法**:
```bash
brew install ffmpeg
```

### Python依存関係エラー

**エラー**: `No module named 'whisperx'`

**解決方法**:
```bash
# 仮想環境を有効化
source venv/bin/activate

# 依存関係を再インストール
pip install -r requirements.txt
```

### PyTorchインストールエラー（Apple Silicon）

**エラー**: `RuntimeError: MPS backend out of memory`

**解決方法**:
```bash
# PyTorchを再インストール
pip uninstall torch torchaudio
pip install torch torchaudio
```

## 🚀 起動時の問題

### Streamlitが起動しない

**エラー**: `streamlit: command not found`

**解決方法**:
```bash
# 仮想環境が有効か確認
which python
# venv/bin/python が表示されるべき

# 有効でない場合
source venv/bin/activate
```

### ポートが使用中

**エラー**: `Port 8501 is already in use`

**解決方法**:
```bash
# 別のポートで起動
streamlit run main.py --server.port 8502

# または既存のプロセスを終了
lsof -ti:8501 | xargs kill -9
```

### ブラウザが開かない

**解決方法**:
手動でブラウザを開き、`http://localhost:8501` にアクセス

## 📝 文字起こしエラー

### メモリ不足

**エラー**: `RuntimeError: CUDA out of memory` または `Cannot allocate memory`

**解決方法**:
1. より小さいモデルを使用（large-v3 → medium → small）
2. 他のアプリケーションを終了
3. 動画を短く分割

### 文字起こしが進まない

**症状**: プログレスバーが0%のまま

**解決方法**:
1. ログを確認: `logs/`フォルダ
2. より短い動画でテスト
3. APIモードを試す

### 文字起こし精度が低い

**解決方法**:
1. より大きいモデル（large-v3）を使用
2. 音声品質を改善（ノイズ除去）
3. APIモードを使用（最新モデル）

## ⚙️ 処理エラー

### 「元の動画に存在しない部分が含まれています」

**原因**: 編集時に元にないテキストを追加

**解決方法**:
- 赤くハイライトされた部分を削除
- 元のテキストから正確にコピー＆ペースト

### FFmpegエラー

**エラー**: `FFmpeg process failed`

**解決方法**:
```bash
# FFmpegを再インストール
brew reinstall ffmpeg

# 動画ファイルの破損確認
ffmpeg -i your_video.mp4 -f null -
```

### 無音削除が機能しない

**解決方法**:
1. 閾値を調整（-35dB → -40dB）
2. 最小無音時間を増やす（0.3秒 → 0.5秒）
3. 音声トラックの確認

## 💾 出力関連

### ファイルが見つからない

**症状**: 処理完了後、出力ファイルが見つからない

**解決方法**:
1. 正しいフォルダを確認: `{動画名}_TextffCut/`
2. ファインダーで検索
3. 権限を確認: `ls -la`

### FCPXMLがインポートできない

**解決方法**:
1. Final Cut Pro / DaVinci Resolveのバージョン確認
2. XMLファイルの整合性確認
3. 動画ファイルのパスが正しいか確認

### 出力動画が再生できない

**解決方法**:
```bash
# コーデック情報を確認
ffmpeg -i output_video.mp4

# 再エンコード
ffmpeg -i output_video.mp4 -c:v libx264 -c:a aac fixed_video.mp4
```

## 🐌 パフォーマンス問題

### 処理が遅い

**最適化方法**:
1. **モデルサイズ**: large-v3 → medium
2. **並列処理**: 自動的に最適化される
3. **APIモード**: GPU環境がない場合は高速

### メモリ使用量が多い

**解決方法**:
1. Activity Monitor でメモリ確認
2. 不要なアプリを終了
3. Docker版の場合、メモリ割り当てを増やす

### 応答が遅い

**解決方法**:
1. ブラウザのキャッシュをクリア
2. 別のブラウザで試す（Chrome推奨）
3. `streamlit cache clear`

## 🔑 API関連

### APIキーエラー

**エラー**: `Invalid API key`

**確認事項**:
1. キーが`sk-`で始まっているか
2. 前後に空白がないか
3. 有効期限が切れていないか

### API料金エラー

**エラー**: `You exceeded your current quota`

**解決方法**:
1. OpenAIダッシュボードで残高確認
2. 料金をチャージ
3. 使用量制限を設定

### APIタイムアウト

**エラー**: `Request timeout`

**解決方法**:
1. より短い動画で分割処理
2. ネットワーク接続を確認
3. 時間を置いて再試行

## 🐳 Docker関連

### コンテナが起動しない

**確認コマンド**:
```bash
# Docker Desktopの状態確認
docker --version

# ログ確認
./docker-run.sh logs

# 手動で起動
docker compose up
```

### ボリュームエラー

**エラー**: `Permission denied`

**解決方法**:
```bash
# 権限を修正
chmod -R 755 videos output logs

# Dockerを再起動
./docker-run.sh restart
```

### メモリ不足（Docker）

**解決方法**:
1. Docker Desktop → Preferences → Resources
2. Memory を 8GB 以上に設定
3. Apply & Restart

## 🆘 それでも解決しない場合

### 情報収集

以下の情報を準備：

1. **環境情報**:
   ```bash
   python setup.py
   ```

2. **エラーログ**:
   ```bash
   cat logs/textffcut_*.log | tail -100
   ```

3. **システム情報**:
   ```bash
   system_profiler SPSoftwareDataType
   python --version
   ffmpeg -version
   ```

### 報告方法

[GitHub Issues](https://github.com/Coidemo/TextffCut/issues) で新しいIssueを作成：

**タイトル**: [エラーの種類] 簡潔な説明

**本文**:
```markdown
## 環境
- macOS: [バージョン]
- Python: [バージョン]
- TextffCut: [バージョン]

## エラー内容
[エラーメッセージ全文]

## 再現手順
1. 
2. 
3. 

## 試したこと
- 
- 

## ログ
[関連するログを添付]
```

## 📚 関連ドキュメント

- [インストールガイド](INSTALL.md)
- [ユーザーガイド](USER_GUIDE.md)
- [Docker ガイド](DOCKER_GUIDE.md)

---

最終更新: 2025-05-31