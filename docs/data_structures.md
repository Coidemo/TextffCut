# TextffCut データ構造定義

## 概要
TextffCutで使用される主要なデータ構造の詳細定義です。AIが実装時に参照するための正確な仕様を記載しています。

## 1. TranscriptionResultV2

文字起こし結果を表現する中心的なデータ構造。

```python
class TranscriptionResultV2:
    """文字起こし結果のV2データモデル"""
    
    # 基本情報
    text: str                          # 全体のテキスト
    segments: List[TranscriptionSegmentV2]  # セグメントリスト
    language: str                      # 言語コード（例: "ja"）
    
    # メタデータ
    processing_time: Optional[float]   # 処理時間（秒）
    model_info: Optional[Dict[str, Any]]  # モデル情報
    
    # 統計情報
    total_duration: Optional[float]    # 音声の総時間（秒）
    word_count: Optional[int]          # 単語数
    
    # メソッド
    def to_dict() -> Dict[str, Any]   # 辞書形式に変換
    def from_dict(data: Dict[str, Any]) -> TranscriptionResultV2  # 辞書から復元
    def to_srt() -> str               # SRT形式に変換
    def merge_segments(threshold: float) -> TranscriptionResultV2  # セグメント結合
```

### JSON形式

```json
{
  "text": "全体のテキスト",
  "segments": [...],
  "language": "ja",
  "processing_time": 123.45,
  "model_info": {
    "name": "whisper-1",
    "type": "api"
  },
  "total_duration": 300.0,
  "word_count": 1500
}
```

## 2. TranscriptionSegmentV2

個別のセグメント（文や段落）を表現。

```python
class TranscriptionSegmentV2:
    """文字起こしセグメント"""
    
    # 必須フィールド
    id: str                           # 一意識別子
    text: str                         # セグメントテキスト
    start: float                      # 開始時間（秒）
    end: float                        # 終了時間（秒）
    
    # アライメント情報
    words: Optional[List[WordInfo]]   # 単語レベル情報
    chars: Optional[List[CharInfo]]   # 文字レベル情報（日本語用）
    alignment_completed: bool = False # アライメント完了フラグ
    alignment_error: Optional[str]    # アライメントエラー
    
    # 信頼度情報
    confidence: Optional[float]       # 信頼度スコア（0-1）
    no_speech_prob: Optional[float]   # 無音確率
    
    # メソッド
    def has_valid_alignment() -> bool # 有効なアライメントがあるか
    def get_duration() -> float       # セグメントの長さ
```

### JSON形式

```json
{
  "id": "seg_001",
  "text": "こんにちは、今日はいい天気ですね。",
  "start": 0.0,
  "end": 3.5,
  "words": [
    {
      "word": "こんにちは",
      "start": 0.0,
      "end": 0.8,
      "confidence": 0.95
    }
  ],
  "confidence": 0.92,
  "alignment_completed": true
}
```

## 3. WordInfo

単語レベルのタイミング情報。

```python
# 辞書形式で保存（Pydanticモデルではない）
WordInfo = {
    "word": str,              # 単語テキスト
    "start": Optional[float], # 開始時間
    "end": Optional[float],   # 終了時間
    "confidence": Optional[float]  # 信頼度
}
```

## 4. キャッシュファイル形式

### ファイル名規則
```
{model_size}_{file_hash}_{api_or_local}_{language}.json
```

例：`medium_a1b2c3d4_local_ja.json`

### ディレクトリ構造
```
transcriptions/
├── medium_a1b2c3d4_local_ja.json
├── large-v3_a1b2c3d4_local_ja.json
└── whisper-1_a1b2c3d4_api_ja.json
```

## 5. セッション状態（Streamlit）

```python
# st.session_state のキー定義
SESSION_KEYS = {
    # 基本情報
    "video_path": str,              # 選択された動画パス
    "transcription_result": TranscriptionResultV2,  # 文字起こし結果
    
    # 編集状態
    "edited_segments": Dict[str, str],  # 編集されたセグメント
    "selected_segments": List[str],     # 選択されたセグメントID
    
    # 処理オプション
    "remove_silence": bool,         # 無音削除フラグ
    "silence_threshold": float,     # 無音閾値
    "pad_before": float,           # 前パディング
    "pad_after": float,            # 後パディング
    
    # 進捗状態
    "processing": bool,            # 処理中フラグ
    "progress": float,             # 進捗（0-1）
    "progress_message": str        # 進捗メッセージ
}
```

## 6. エラー情報構造

```python
ErrorInfo = {
    "error_code": str,          # エラーコード
    "message": str,             # 開発者向けメッセージ
    "user_message": str,        # ユーザー向けメッセージ
    "severity": str,            # 重要度（info/warning/error/critical）
    "recoverable": bool,        # 回復可能かどうか
    "details": Dict[str, Any],  # 詳細情報
    "timestamp": str            # ISO形式のタイムスタンプ
}
```

## 7. 設定ファイル構造（config.yaml）

```yaml
transcription:
  model_size: "medium"          # 固定（要件定義により）
  device: "auto"               # cpu/cuda/auto
  compute_type: "int8"         # 計算精度
  batch_size: 8                # バッチサイズ
  
video:
  silence_threshold: -35       # dB
  min_silence_duration: 0.3    # 秒
  min_segment_duration: 0.3    # 秒
  
paths:
  cache_dir: "transcriptions"  # キャッシュディレクトリ
  temp_dir: "temp_wav"        # 一時ファイルディレクトリ
  output_dir: "output"        # 出力ディレクトリ
```

## 使用上の注意

1. **型の一貫性**: WordInfoとCharInfoは辞書形式で保持（クラスではない）
2. **時間の単位**: すべての時間は秒単位（float）
3. **IDの形式**: セグメントIDは "seg_" プレフィックスを推奨
4. **キャッシュ**: ファイルハッシュは名前・サイズ・更新時刻から生成
5. **エンコーディング**: すべてのJSONファイルはUTF-8