# Dockerイメージサイズ削減計画

## 現状
- v0.9.7-beta: 13.1GB
- 目標: 5-6GB（v0.9.6と同等レベル）

## 削減方法（優先度順）

### 1. Whisperモデルの変更（最大削減効果）
**現在**: medium（1.5GB）
**提案**: 
- **small（500MB）**: 精度は若干落ちるが実用的
- **base（150MB）**: 短い動画や明瞭な音声なら十分
- **削減効果**: 1-1.35GB

### 2. CPU版PyTorch（実施済み）
- GPU版からCPU版に変更
- **削減効果**: 1-2GB

### 3. マルチステージビルド（実施済み）
- ビルド時の不要ファイルを除外
- **削減効果**: 0.5-1GB

### 4. アライメントモデルの扱い
**現在**: 日本語アライメントモデル同梱（500MB）
**提案**: 
- 初回実行時にダウンロード（v0.9.6方式）
- または軽量な代替手法を検討
- **削減効果**: 500MB

### 5. 不要なPythonパッケージ削除
```bash
# 削除候補
- matplotlib（グラフ描画なし）
- jupyter関連（開発用）
- テスト関連パッケージ
```
**削減効果**: 200-300MB

### 6. Alpine Linuxベース（リスクあり）
```dockerfile
FROM python:3.11-alpine
```
- 互換性問題の可能性あり
- **削減効果**: 300-500MB

### 7. pip wheelキャッシュの完全削除
```dockerfile
RUN pip install --no-cache-dir --no-compile -r requirements.txt && \
    rm -rf /root/.cache/pip/* && \
    find /usr/local -type d -name __pycache__ -exec rm -rf {} + || true
```
**削減効果**: 100-200MB

### 8. 実行時のモデル選択機能
環境変数でモデルサイズを選択可能に：
```python
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'small')  # tiny/base/small/medium
```

## 推奨構成

### A. バランス重視（推奨）
- Whisper small + CPU版PyTorch + マルチステージビルド
- **予想サイズ**: 6-7GB
- **精度**: 実用レベル維持

### B. サイズ最優先
- Whisper base + Alpine Linux + アライメントなし
- **予想サイズ**: 4-5GB
- **精度**: 短時間動画向け

### C. 精度重視
- Whisper medium + 最適化のみ
- **予想サイズ**: 8-9GB
- **精度**: 高精度維持