# TextffCut 完全機能版サマリー

## 実装した3つのバージョン

### 1. 軽量CLI版（textffcut_cli_lite.py）✅
- **サイズ**: 7.1MB
- **機能**: 無音検出・削除、FCPXMLエクスポート
- **依存**: ffmpegのみ
- **用途**: シンプルな無音削除タスク

### 2. フル機能CLI版（textffcut_full.py）🎯
- **機能**: 
  - WhisperXによる文字起こし
  - アライメント（文字レベルの時間情報）
  - テキスト差分検出
  - 無音削除
  - FCPXMLエクスポート
- **依存**: WhisperX、PyTorch、core/モジュール
- **用途**: 本格的な動画編集ワークフロー

### 3. GUI版（textffcut_gui.py）🖥️
- **フレームワーク**: Streamlit
- **機能**: フル機能CLI版と同等
- **特徴**: 
  - ビジュアルなインターフェース
  - リアルタイムプログレス表示
  - 結果のプレビュー

## コアワークフロー

```
1. 動画をWhisperXで文字起こし
   ↓
2. アライメントで文字レベルの時間情報を取得
   ↓
3. オリジナル/編集後テキストの差分を検出
   ↓
4. 差分箇所の時間範囲を特定
   ↓
5. 無音部分を削除（オプション）
   ↓
6. FCPXMLとして編集ソフト用にエクスポート
```

## 使用例

### フル機能CLI版
```bash
# 完全なワークフロー
python textffcut_full.py full video.mp4 \
  --original original.txt \
  --target edited.txt \
  --model large \
  --remove-silence

# 文字起こしのみ
python textffcut_full.py transcribe video.mp4 --model large --language ja

# 差分検出（保存済み文字起こし使用）
python textffcut_full.py diff video.mp4 \
  --transcription result.json \
  --original orig.txt \
  --target edited.txt
```

### GUI版
```bash
streamlit run textffcut_gui.py
```

## アーキテクチャ

```
textffcut_full.py / textffcut_gui.py
    ├── core/
    │   ├── transcription.py    # WhisperX統合
    │   ├── text_processor.py   # テキスト差分検出
    │   ├── video.py           # 無音検出・動画処理
    │   └── export.py          # FCPXML/EDLエクスポート
    └── utils/
        ├── logging.py         # ログ管理
        └── progress.py        # プログレス表示
```

## PyInstallerでのビルド課題

### 軽量版（成功）✅
- ffmpegのみ使用 → 7.1MB

### フル機能版（課題）⚠️
- WhisperX + PyTorch → 1GB以上
- 複雑な依存関係
- GPU対応の問題

## 推奨デプロイ方法

### 1. 開発者向け
```bash
# 環境構築
pip install -r requirements.txt

# 実行
python textffcut_full.py full video.mp4 --original orig.txt --target edited.txt
```

### 2. 一般ユーザー向け
- **Option A**: Docker版（メモリ最適化済み）
- **Option B**: 軽量CLI版（無音削除のみ）
- **Option C**: Streamlit Cloud（Web版）

## まとめ

TextffCutの本来の機能であるWhisperXアライメントとテキスト差分検出を実装しました。
GUI版も含めて、完全な動画編集ワークフローを提供できるようになりました。

### 課題と解決策
- **ビルドサイズ**: PyTorchが大きいため、Docker版かWeb版を推奨
- **Windows対応**: WSL2 + Dockerまたは軽量版を使用
- **GUI**: Streamlitで実装済み、Flet版は将来の選択肢