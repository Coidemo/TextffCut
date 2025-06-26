# インタラクティブ波形選択機能の設計（改訂版）

## 参考事例：Zennの波形編集アプリ
https://zenn.dev/sabigara/articles/95f2eb0fffac3f

Reactベースの波形編集アプリの実装から学ぶ：
- **直感的な操作**: ドラッグ、クリック、ズームなどの操作
- **視覚的フィードバック**: 選択状態、ホバー効果
- **パフォーマンス**: Canvas/WebGLベースの描画

## 1. 現状の問題点

現在のタイムライン編集UIは以下の問題を抱えている：
- ドロップダウンによるセグメント選択が直感的でない
- 波形を見ながら選択できない
- 編集したい箇所を視覚的に特定しづらい

## 2. 調査結果

### 2.1 技術的な実現可能性

#### Streamlit Native Support (推奨)
```python
# Streamlit 1.35.0以降で利用可能
event = st.plotly_chart(fig, key="waveform", on_select="rerun")
if event and event.selection:
    # 選択された範囲の処理
    box_select = event.selection.box
    lasso_select = event.selection.lasso
    points = event.selection.points
```

**メリット:**
- 追加ライブラリ不要
- Streamlitの公式サポート
- パフォーマンスが良好

**デメリット:**
- 選択イベントのみサポート（クリックイベントは未対応）
- カスタマイズ性に制限

#### Streamlit-plotly-events
```python
from streamlit_plotly_events import plotly_events
selected_points = plotly_events(fig, click_event=True)
```

**メリット:**
- クリックイベントをサポート
- より細かい制御が可能

**デメリット:**
- 外部ライブラリの依存
- レイアウトが崩れる場合がある

### 2.2 参考プロジェクト

#### BeatInspect
- GitHub: stefanrmmr/beatinspect
- Streamlit + Plotlyで音声波形の可視化
- スペクトログラムとの同期表示

#### Dash Audio Components
- カスタムコンポーネントで音声編集機能を実装
- 波形上でのドラッグ選択

## 3. Streamlitでの現実的な実装方式

### 前提：Streamlitの制約
- Reactのような細かいインタラクションは困難
- Canvas/WebGLの直接操作は不可
- しかし、Plotlyを活用すれば十分なインタラクティビティを実現可能

## 4. 改訂版：実装方式

### 3.1 段階的実装計画

#### Phase 1: 基本的なクリック選択（即実装可能）
```python
# 波形を分割表示し、クリック可能な領域として定義
fig = go.Figure()

# 各セグメントを個別のトレースとして追加
for i, segment in enumerate(segments):
    fig.add_trace(go.Scatter(
        x=time_data,
        y=waveform_data,
        mode='lines',
        name=f'segment_{i}',
        customdata=[i] * len(time_data),  # セグメントIDを保持
        hovertemplate='セグメント %{customdata}<br>時間: %{x:.2f}秒'
    ))

# Plotlyのbox選択を使用
fig.update_layout(
    dragmode='select',
    selectdirection='h'  # 水平方向のみ選択可能
)

# 選択イベントの処理
event = st.plotly_chart(fig, on_select="rerun")
if event and event.selection and event.selection.points:
    # 選択されたポイントからセグメントIDを取得
    selected_segment_ids = set()
    for point in event.selection.points:
        segment_id = point['customdata'][0]
        selected_segment_ids.add(segment_id)
```

#### Phase 2: ホバー＋クリックの組み合わせ
```python
# セグメント境界にマーカーを配置
for i, boundary in enumerate(segment_boundaries):
    fig.add_vline(
        x=boundary,
        line_color="orange",
        line_width=3,
        opacity=0.3,
        annotation_text=f"クリックで選択",
        annotation_position="top"
    )

# ホバー時にハイライト
fig.update_traces(
    hoverlabel=dict(bgcolor="white", font_size=16),
    selector=dict(mode='markers+lines')
)
```

#### Phase 3: カスタムコンポーネント（将来的な拡張）
- React.jsベースのカスタムコンポーネント開発
- WaveSurfer.jsやPeaks.jsの統合
- より高度な編集機能の実装

### 3.2 UIデザイン

```
┌─────────────────────────────────────────────────────────┐
│ タイムライン編集                                          │
├─────────────────────────────────────────────────────────┤
│ 💡 波形をクリックまたはドラッグしてセグメントを選択      │
├─────────────────────────────────────────────────────────┤
│ [全体波形表示 - クリック可能]                            │
│                                                         │
│ ▼ セグメント1  ▼ セグメント2  ▼ セグメント3           │
│ ├────────────┼──────────────┼────────────┤             │
│ │   ～～～   │    ～～～～   │   ～～    │ ← 波形      │
│ ├────────────┼──────────────┼────────────┤             │
│   ↑ クリックで選択  ↑ ホバーでハイライト               │
├─────────────────────────────────────────────────────────┤
│ 選択中: セグメント2                                      │
│ [選択セグメントの詳細波形と編集コントロール]             │
└─────────────────────────────────────────────────────────┘
```

### 3.3 実装上の工夫

#### パフォーマンス最適化
```python
# 大きな波形データのダウンサンプリング
def downsample_waveform(waveform, target_points=5000):
    if len(waveform) <= target_points:
        return waveform
    
    # ピークを保持しながらダウンサンプリング
    chunk_size = len(waveform) // target_points
    downsampled = []
    
    for i in range(0, len(waveform), chunk_size):
        chunk = waveform[i:i+chunk_size]
        # 最大値と最小値を交互に取得（波形の形状を保持）
        if i % 2 == 0:
            downsampled.append(np.max(chunk))
        else:
            downsampled.append(np.min(chunk))
    
    return np.array(downsampled)
```

#### セグメント識別の改善
```python
# 各セグメントに異なる色を割り当て
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

for i, segment in enumerate(segments):
    color = colors[i % len(colors)]
    
    # セグメント領域を半透明の矩形で表示
    fig.add_vrect(
        x0=segment['start'],
        x1=segment['end'],
        fillcolor=color,
        opacity=0.2,
        layer="below",
        line_width=0,
    )
```

## 4. 実装手順

### Step 1: Plotly選択イベントの実装
1. 現在のドロップダウンを削除
2. 波形表示にbox選択機能を追加
3. 選択イベントハンドラーの実装

### Step 2: セグメント視覚化の改善
1. セグメントごとの色分け
2. ホバー時のハイライト
3. 境界線の明確化

### Step 3: ユーザビリティの向上
1. 選択方法の説明テキスト追加
2. キーボードショートカットとの連携
3. 選択状態の視覚的フィードバック

## 5. 代替案

### 5.1 セグメントボタン配置方式
波形の下に各セグメントのボタンを時間軸に沿って配置：
```python
# 波形表示の下にボタンを配置
cols = st.columns(len(segments))
for i, (segment, col) in enumerate(zip(segments, cols)):
    with col:
        if st.button(f"S{i+1}", key=f"seg_btn_{i}"):
            st.session_state.selected_segment_idx = i
```

### 5.2 タイムライン＋サムネイル方式
各セグメントの波形サムネイルをタイル状に表示：
```python
# グリッドレイアウトでサムネイル表示
cols_per_row = 3
for i in range(0, len(segments), cols_per_row):
    cols = st.columns(cols_per_row)
    for j, col in enumerate(cols):
        if i + j < len(segments):
            with col:
                # 小さな波形表示
                render_segment_thumbnail(segments[i+j])
                if st.button("選択", key=f"select_{i+j}"):
                    st.session_state.selected_segment_idx = i+j
```

## 6. リスク評価

### 技術的リスク
- Plotlyの選択イベントの制限
- 大きな波形データでのパフォーマンス
- ブラウザ互換性

### 対策
- 段階的な実装でリスクを最小化
- パフォーマンステストの実施
- フォールバック機能の実装

## 7. 推奨実装

**Phase 1の実装を推奨**
- Streamlit標準機能で実現可能
- 実装が簡単で保守性が高い
- ユーザビリティの大幅な改善が期待できる

box選択またはlasso選択により、視覚的にセグメントを選択できるようになり、現在のドロップダウン方式よりも直感的な操作が可能になる。