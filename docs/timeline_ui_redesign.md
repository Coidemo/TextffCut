# タイムライン編集UI再設計

## 現在の問題点
1. セグメントごとに個別に表示され、全体像が把握しづらい
2. 「編集を完了」ボタンが機能しない（Streamlit内でのreturn問題）
3. 操作が直感的でない

## DaVinci Resolve風タイムラインUIの設計

### 1. 全体レイアウト
```
┌─────────────────────────────────────────────────────┐
│ タイムライン編集                                      │
├─────────────────────────────────────────────────────┤
│ [00:00:00]                              [01:30:00]  │
│ ├────┬─────┬──────┬────┬───────┬─────┤             │
│ │ S1 │ S2  │  S3  │ S4 │   S5  │ S6  │             │
│ ├────┴─────┴──────┴────┴───────┴─────┤             │
│ ▲ 波形表示（全セグメント連続表示）                    │
├─────────────────────────────────────────────────────┤
│ 選択中: セグメント3                                   │
│ 開始: 00:15:30 | 終了: 00:18:45 | 長さ: 00:03:15   │
│ [↑/↓: ±0.1秒] [Shift+↑/↓: ±1.0秒]                 │
├─────────────────────────────────────────────────────┤
│ [編集を完了] [リセット] [キャンセル]                  │
└─────────────────────────────────────────────────────┘
```

### 2. 実装方針

#### 2.1 横並び波形表示
- 全セグメントの波形を1つの連続したグラフとして表示
- セグメント境界を縦線で表示
- クリック/ドラッグで境界を調整可能

#### 2.2 セッション状態の改善
```python
# 編集完了フラグをセッション状態で管理
if st.button("編集を完了"):
    st.session_state.timeline_editing_completed = True
    st.session_state.adjusted_time_ranges = service.get_adjusted_time_ranges()
    st.rerun()

# main.pyで確認
if st.session_state.get("timeline_editing_completed", False):
    adjusted_ranges = st.session_state.adjusted_time_ranges
    # クリーンアップ
    del st.session_state.timeline_editing_completed
```

#### 2.3 インタラクティブ機能
- セグメントをクリックで選択
- 境界線をドラッグで調整
- キーボードショートカットで微調整
- リアルタイムプレビュー

### 3. 実装ステップ

#### Step 1: 基本的な横並びタイムライン実装
- 全セグメントの波形データを結合
- Plotlyで統合グラフを作成
- セグメント境界の表示

#### Step 2: インタラクション追加
- セグメント選択機能
- 境界調整機能
- キーボードショートカット

#### Step 3: UI/UXの改善
- アニメーション追加
- ツールチップ表示
- ズーム/パン機能

### 4. 技術的課題と解決策

#### 4.1 大量の波形データ処理
- ダウンサンプリング（表示用の低解像度版を作成）
- 遅延読み込み（表示範囲のみ高解像度化）

#### 4.2 Streamlitの制約
- st.plotly_chartのクリックイベント非対応
  → カスタムコンポーネントの検討
  → または、スライダーベースの調整UI

#### 4.3 パフォーマンス
- 波形データのキャッシュ
- 差分更新のみ実行

### 5. 代替案：シンプルなスライダーベースUI

Plotlyのインタラクティブ機能が制限される場合：

```python
# 全セグメントを横並びで表示（読み取り専用）
st.plotly_chart(combined_waveform_figure)

# 各セグメントの境界をスライダーで調整
for i, segment in enumerate(segments):
    col1, col2 = st.columns(2)
    with col1:
        new_start = st.slider(
            f"セグメント{i+1} 開始",
            min_value=prev_end,
            max_value=segment.end - 0.1,
            value=segment.start,
            step=0.1
        )
    with col2:
        new_end = st.slider(
            f"セグメント{i+1} 終了",
            min_value=new_start + 0.1,
            max_value=next_start,
            value=segment.end,
            step=0.1
        )
```