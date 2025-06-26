# 実用的な波形インタラクション実装計画

## 現状の問題分析

Zennの記事の波形エディタは素晴らしいが、Streamlitの制約により同等の実装は困難：
- Reactのようなリアルタイムインタラクション不可
- WebAudio APIの直接操作不可
- カスタムCanvasレンダリング不可

## 実装可能な解決策

### 方式1: セグメントボタン付き波形表示（最も現実的）

```python
def render_waveform_with_buttons(video_path: str, segments: list, selected_idx: int):
    """波形表示とセグメントボタンを組み合わせた実装"""
    
    # 波形表示
    fig = go.Figure()
    
    # 全セグメントの波形を一つのグラフに表示
    current_x = 0
    segment_positions = []
    
    for i, segment in enumerate(segments):
        # セグメントごとに異なる色
        color = '#FF6B6B' if i == selected_idx else '#4ECDC4'
        
        # 波形データ取得（簡略化）
        duration = segment['end'] - segment['start']
        x = np.linspace(current_x, current_x + duration, 1000)
        y = np.random.randn(1000) * 0.5  # 実際は波形データ
        
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode='lines',
            name=f'Segment {i+1}',
            line=dict(color=color, width=2 if i == selected_idx else 1),
            fill='tozeroy',
            fillcolor=f'{color}40',
            showlegend=False
        ))
        
        # セグメント境界
        if i > 0:
            fig.add_vline(x=current_x, line_dash="dash", line_color="gray")
        
        segment_positions.append((current_x, current_x + duration, i))
        current_x += duration
    
    # レイアウト設定
    fig.update_layout(
        height=200,
        margin=dict(l=0, r=0, t=30, b=0),
        title="クリックしたいセグメントのボタンを押してください"
    )
    
    # 波形表示
    st.plotly_chart(fig, use_container_width=True)
    
    # セグメントボタンを波形の時間軸に合わせて配置
    # カラム数を動的に設定
    button_container = st.container()
    with button_container:
        # CSSで横スクロール可能にする
        st.markdown("""
        <style>
        .segment-buttons {
            display: flex;
            overflow-x: auto;
            gap: 2px;
            padding: 10px 0;
        }
        .segment-button {
            flex-shrink: 0;
            padding: 5px 15px;
            border-radius: 5px;
            cursor: pointer;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # ボタンを配置
        cols = st.columns(len(segments))
        for i, (col, segment) in enumerate(zip(cols, segments)):
            with col:
                if st.button(
                    f"セグメント{i+1}\n{format_time(segment['start'])}", 
                    key=f"seg_{i}",
                    use_container_width=True,
                    type="primary" if i == selected_idx else "secondary"
                ):
                    return i
    
    return selected_idx
```

### 方式2: クリッカブルな波形領域（実験的）

```python
def render_clickable_waveform(segments, selected_idx):
    """クリック可能な領域を持つ波形"""
    
    fig = make_subplots(
        rows=1, cols=len(segments),
        shared_yaxes=True,
        horizontal_spacing=0.01
    )
    
    for i, segment in enumerate(segments):
        # 各セグメントを別のサブプロットとして配置
        waveform_data = get_waveform_data(segment)
        
        fig.add_trace(
            go.Scatter(
                x=waveform_data['time'],
                y=waveform_data['amplitude'],
                mode='lines',
                fill='tozeroy',
                fillcolor='rgba(255,107,107,0.3)' if i == selected_idx else 'rgba(78,205,196,0.3)',
                line=dict(color='#FF6B6B' if i == selected_idx else '#4ECDC4'),
                name=f'Segment {i+1}',
                customdata=[i] * len(waveform_data['time']),
                hovertemplate='セグメント %{customdata}<br>クリックで選択'
            ),
            row=1, col=i+1
        )
    
    # レイアウト
    fig.update_layout(
        height=250,
        showlegend=False,
        hovermode='closest'
    )
    
    # クリックイベントのシミュレーション
    # Streamlitのexperimental機能を使用
    clicked = plotly_events(fig, click_event=True, select_event=False)
    
    if clicked:
        # クリックされたセグメントを特定
        point_data = clicked[0]
        if 'customdata' in point_data:
            return point_data['customdata'][0]
    
    return selected_idx
```

### 方式3: タイムライン風セグメント選択（推奨）

```python
def render_timeline_selector(segments, selected_idx):
    """タイムライン風のセグメント選択UI"""
    
    st.markdown("### 🎯 セグメントをクリックして選択")
    
    # 全体の時間を計算
    total_duration = max(seg['end'] for seg in segments)
    
    # タイムラインコンテナ
    timeline_container = st.container()
    
    with timeline_container:
        # プログレスバー風の表示
        fig = go.Figure()
        
        # 背景のタイムライン
        fig.add_trace(go.Scatter(
            x=[0, total_duration],
            y=[0, 0],
            mode='lines',
            line=dict(color='lightgray', width=20),
            showlegend=False
        ))
        
        # 各セグメントを矩形で表示
        for i, segment in enumerate(segments):
            # セグメントの矩形
            fig.add_shape(
                type="rect",
                x0=segment['start'], x1=segment['end'],
                y0=-0.4, y1=0.4,
                fillcolor='#FF6B6B' if i == selected_idx else '#4ECDC4',
                opacity=0.8 if i == selected_idx else 0.6,
                line=dict(color='darkred' if i == selected_idx else 'darkblue', width=2)
            )
            
            # セグメント番号
            fig.add_annotation(
                x=(segment['start'] + segment['end']) / 2,
                y=0,
                text=str(i + 1),
                showarrow=False,
                font=dict(size=14, color='white')
            )
        
        # レイアウト
        fig.update_layout(
            height=100,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=True,
                tickformat='.1f',
                title='時間（秒）'
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                range=[-0.5, 0.5]
            ),
            plot_bgcolor='white',
            hovermode='x'
        )
        
        # 表示
        st.plotly_chart(fig, use_container_width=True)
        
        # セグメント選択ボタン（タイムラインの下）
        cols = st.columns(len(segments))
        for i, (col, segment) in enumerate(zip(cols, segments)):
            with col:
                if st.button(
                    f"{i+1}",
                    key=f"timeline_seg_{i}",
                    use_container_width=True,
                    help=f"{format_time(segment['start'])} - {format_time(segment['end'])}"
                ):
                    return i
    
    # 選択中のセグメント情報
    if selected_idx < len(segments):
        selected = segments[selected_idx]
        st.info(f"選択中: セグメント {selected_idx + 1} "
                f"({format_time(selected['start'])} - {format_time(selected['end'])})")
    
    return selected_idx
```

### 実装の優先順位

1. **方式3（タイムライン風）を最優先で実装**
   - 視覚的にわかりやすい
   - Streamlitの制約内で実現可能
   - ボタンとビジュアルの組み合わせ

2. **方式1（ボタン付き波形）を次に実装**
   - 波形を見ながら選択可能
   - 実装が比較的簡単

3. **方式2（クリッカブル波形）は将来的な拡張として検討**
   - streamlit-plotly-eventsが必要
   - パフォーマンスの課題あり

## コード例：即座に実装可能なバージョン

```python
def render_improved_segment_selector(segments, selected_idx, video_path):
    """改善されたセグメント選択UI"""
    
    # タイトル
    st.markdown("### 📊 セグメント選択")
    
    # 方法1: 番号ボタングリッド（シンプル）
    st.markdown("#### 方法1: クイック選択")
    cols = st.columns(min(len(segments), 6))  # 最大6列
    
    for i, segment in enumerate(segments):
        col_idx = i % len(cols)
        with cols[col_idx]:
            button_type = "primary" if i == selected_idx else "secondary"
            if st.button(
                f"#{i+1}\n{format_time(segment['start'])}",
                key=f"quick_{i}",
                use_container_width=True,
                type=button_type
            ):
                return i
    
    # 方法2: リスト表示（詳細）
    with st.expander("詳細リスト表示", expanded=False):
        for i, segment in enumerate(segments):
            col1, col2, col3 = st.columns([1, 3, 1])
            
            with col1:
                st.write(f"**#{i+1}**")
            
            with col2:
                st.write(f"{format_time(segment['start'])} - {format_time(segment['end'])}")
                st.caption(segment.get('text', '')[:50] + "...")
            
            with col3:
                if st.button("選択", key=f"list_{i}"):
                    return i
            
            if i == selected_idx:
                st.markdown("👆 **選択中**")
    
    return selected_idx
```

これらの実装は、Streamlitの制約内で動作し、ユーザーにとって使いやすいインターフェースを提供します。