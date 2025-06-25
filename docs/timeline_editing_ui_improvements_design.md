# タイムライン編集UI改善 - 基本設計書

## 1. 設計概要

### 1.1 目的
タイムライン編集機能のユーザビリティを向上させ、より直感的で効率的な操作を可能にする。

### 1.2 設計方針
- **段階的実装**: 基本機能から順次拡張していく
- **既存機能との互換性**: 現在の機能を損なわない
- **パフォーマンス優先**: 大規模データでも快適に動作
- **Streamlitの制約内での最適化**: カスタムコンポーネントは最小限に

## 2. 機能設計

### 2.1 Phase 1: 波形表示機能

#### 2.1.1 概要
各セグメントの音声波形を視覚的に表示し、音声の強弱や無音部分を直感的に把握できるようにする。

#### 2.1.2 表示仕様
```
[セグメント選択ドロップダウン]
┌────────────────────────────────────────────────────┐
│ セグメント 0001: 00:00:00.0 - 00:00:05.2          │
│ ┌──────────────────────────────────────────────┐ │
│ │     ╱╲    ╱╲                    ╱╲           │ │
│ │    ╱  ╲  ╱  ╲    ╱╲    ╱╲    ╱  ╲          │ │
│ │   ╱    ╲╱    ╲  ╱  ╲  ╱  ╲  ╱    ╲         │ │
│ │__╱______╲______╲╱____╲╱____╲╱______╲________│ │
│ │ 0s     1s     2s     3s     4s     5s        │ │
│ └──────────────────────────────────────────────┘ │
│ "6月5日の木曜日かな木曜日..."                     │
└────────────────────────────────────────────────────┘
```

#### 2.1.3 データ構造
```python
class WaveformData:
    segment_id: str
    sample_rate: int
    samples: list[float]  # 正規化された振幅値 (-1.0 ~ 1.0)
    duration: float
    
class WaveformDisplay:
    width: int = 800     # ピクセル幅
    height: int = 200    # ピクセル高さ
    color_positive: str = "#4CAF50"
    color_negative: str = "#2196F3"
    background: str = "#f0f0f0"
```

#### 2.1.4 処理フロー
1. **波形データ生成**
   ```python
   def generate_waveform_data(video_path: str, start: float, end: float) -> WaveformData:
       # 1. 音声データを抽出（librosa使用）
       # 2. リサンプリング（表示用に間引き）
       # 3. 正規化
       # 4. キャッシュに保存
   ```

2. **描画処理**
   ```python
   def render_waveform(waveform_data: WaveformData) -> plotly.Figure:
       # 1. データポイントを描画用に変換
       # 2. Plotlyでインタラクティブグラフ生成
       # 3. タイムライン表示
   ```

### 2.2 Phase 2: インタラクティブ操作

#### 2.2.1 セグメント境界のドラッグ調整
```
┌──────────────────────────────────────────────────┐
│ ├─────────────┤◆├─────────────┤◆├──────────────┤ │
│   Segment A    ↑   Segment B    ↑   Segment C     │
│              ドラッグ可能      ドラッグ可能        │
└──────────────────────────────────────────────────┘
```

#### 2.2.2 実装方法
- Streamlit-plotlyのクリックイベントを活用
- 境界付近のクリックを検出して調整モードに移行
- Shift+クリックで0.1秒単位の微調整

#### 2.2.3 制約事項
- リアルタイムドラッグは困難（Streamlitの制限）
- クリック→数値入力→確定の3ステップ方式を採用

### 2.3 Phase 3: キーボードショートカット

#### 2.3.1 ショートカット一覧
| キー | 動作 | 備考 |
|------|------|------|
| Space | 再生/停止 | 選択中のセグメント |
| ← / → | 前後のセグメントへ移動 | - |
| ↑ / ↓ | 開始/終了時間を0.5秒調整 | - |
| Shift + ← / → | 開始/終了時間を0.1秒調整 | 微調整 |
| Ctrl + Z | 元に戻す | 最大10回 |
| Ctrl + Y | やり直し | - |

#### 2.3.2 実装アプローチ
```python
# Streamlit-keyupイベントハンドラー
def handle_keyboard_event(key_event):
    if key_event.key == "Space":
        toggle_playback()
    elif key_event.key == "ArrowLeft":
        if key_event.shift:
            adjust_time("start", -0.1)
        else:
            select_previous_segment()
```

## 3. UI/UXデザイン

### 3.1 レイアウト改善

#### 3.1.1 現在のレイアウト
```
[統計情報]
[データフレーム]
[セグメント選択]
[時間調整UI]
[プレビュー]
[操作ボタン]
```

#### 3.1.2 改善後のレイアウト
```
┌─────────────────────────────────────────────────────┐
│ [統計情報バー]                                      │
├─────────────────────────────────────────────────────┤
│ ┌───────────────┐ ┌─────────────────────────────┐ │
│ │               │ │                               │ │
│ │  セグメント   │ │      波形表示エリア          │ │
│ │   リスト      │ │                               │ │
│ │               │ ├─────────────────────────────┤ │
│ │               │ │      時間調整パネル          │ │
│ └───────────────┘ └─────────────────────────────┘ │
│ [操作ボタンバー]                                    │
└─────────────────────────────────────────────────────┘
```

### 3.2 カラースキーム

#### 3.2.1 ライトモード
- **波形**: 緑系（音声あり）、グレー（無音）
- **選択中セグメント**: 青系のハイライト
- **境界マーカー**: オレンジ系
- **背景**: ライトグレー

#### 3.2.2 ダークモード
- **波形**: 
  - 音声あり: #4DB6AC（明るいティール）
  - 無音部分: #546E7A（ブルーグレー）
- **選択中セグメント**: #64B5F6（明るい青）
- **境界マーカー**: #FFB74D（明るいオレンジ）
- **背景**: #263238（ダークブルーグレー）
- **グリッド線**: #37474F（ミディアムグレー）
- **テキスト**: #ECEFF1（明るいグレー）
- **タイムラインハイライト**: rgba(100, 181, 246, 0.2)（半透明の青）

#### 3.2.3 実装方法
```python
def get_color_scheme(is_dark_mode: bool) -> dict:
    if is_dark_mode:
        return {
            "waveform_positive": "#4DB6AC",
            "waveform_negative": "#4DB6AC",
            "waveform_silence": "#546E7A",
            "segment_highlight": "#64B5F6",
            "boundary_marker": "#FFB74D",
            "background": "#263238",
            "grid_color": "#37474F",
            "text_color": "#ECEFF1",
            "timeline_hover": "rgba(100, 181, 246, 0.2)"
        }
    else:
        return {
            "waveform_positive": "#4CAF50",
            "waveform_negative": "#2196F3",
            "waveform_silence": "#9E9E9E",
            "segment_highlight": "#2196F3",
            "boundary_marker": "#FF9800",
            "background": "#f0f0f0",
            "grid_color": "#e0e0e0",
            "text_color": "#212121",
            "timeline_hover": "rgba(33, 150, 243, 0.1)"
        }
```

## 4. 技術仕様

### 4.1 依存ライブラリ
```python
# requirements.txtに追加
librosa>=0.10.0    # 音声処理
plotly>=5.18.0     # インタラクティブグラフ
numpy>=1.24.0      # 数値計算（既存）
```

### 4.2 パフォーマンス最適化

#### 4.2.1 波形データのキャッシング
```python
@st.cache_data
def get_waveform_cache_key(video_path: str, segment_id: str) -> str:
    return f"waveform_{hashlib.md5(video_path.encode()).hexdigest()}_{segment_id}"

@st.cache_data(ttl=3600)  # 1時間キャッシュ
def load_waveform_data(video_path: str, start: float, end: float) -> WaveformData:
    # 実装
```

#### 4.2.2 データ間引き戦略
- 表示幅800pxに対して最大1600サンプル
- 長時間セグメントは適応的にダウンサンプリング
- ズーム時は詳細度を上げる

### 4.3 エラーハンドリング
```python
class WaveformError(Exception):
    """波形処理関連のエラー"""
    pass

class AudioExtractionError(WaveformError):
    """音声抽出エラー"""
    pass

class WaveformRenderError(WaveformError):
    """波形描画エラー"""
    pass
```

## 5. 実装計画

### 5.1 Phase 1 実装タスク（2日）
1. **波形データ処理モジュール作成**（0.5日）
   - `core/waveform_processor.py`
   - 音声抽出、リサンプリング、正規化

2. **波形表示コンポーネント作成**（0.5日）
   - `ui/components/waveform_display.py`
   - Plotlyグラフ生成

3. **既存UIへの統合**（0.5日）
   - `ui/timeline_editor.py`の改修
   - レイアウト調整

4. **テスト・デバッグ**（0.5日）
   - 単体テスト作成
   - 統合テスト

### 5.2 Phase 2 実装タスク（2日）
1. **インタラクションハンドラー実装**（1日）
2. **キーボードショートカット実装**（0.5日）
3. **テスト・デバッグ**（0.5日）

### 5.3 Phase 3 実装タスク（2日）
1. **ズーム機能実装**（1日）
2. **詳細編集モード**（0.5日）
3. **テスト・デバッグ**（0.5日）

## 6. テスト計画

### 6.1 単体テスト
- 波形データ生成の正確性
- キャッシュ機能の動作
- エラーハンドリング

### 6.2 統合テスト
- 既存機能との連携
- パフォーマンステスト（90分動画）
- ブラウザ互換性テスト

### 6.3 ユーザビリティテスト
- 操作の直感性
- レスポンス速度
- エラー時の挙動

## 7. リスクと対策

| リスク | 対策 |
|--------|------|
| 大容量ファイルでのメモリ不足 | ストリーミング処理、段階的読み込み |
| Streamlitの描画性能限界 | データ間引き、部分描画 |
| ブラウザ間の挙動差異 | Chrome/Firefox/Safariでのテスト |

## 8. 将来の拡張性

### 8.1 考慮事項
- カスタムStreamlitコンポーネント化
- リアルタイムコラボレーション機能
- AIによる自動境界調整提案

### 8.2 インターフェース設計
```python
class TimelineEditorInterface(ABC):
    @abstractmethod
    def render_waveform(self, segment: TimelineSegment) -> Any:
        pass
    
    @abstractmethod
    def handle_interaction(self, event: InteractionEvent) -> None:
        pass
```

---

作成日: 2025-01-25
作成者: Claude
承認者: （未承認）