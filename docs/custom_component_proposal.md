# TextffCut カスタムコンポーネント実装提案

## 概要
Streamlit Custom Components（React + TypeScript）を使用して、より高度なタイムライン編集機能を実装する提案。

## 実装可能な機能

### 1. 高度なタイムライン編集コンポーネント
```typescript
interface TimelineEditorProps {
  clips: Array<{
    id: string;
    startTime: number;
    endTime: number;
    waveform: number[];
  }>;
  onUpdate: (clips: Clip[]) => void;
}
```

**機能：**
- ✅ ドラッグ＆ドロップでクリップ境界を調整
- ✅ 波形のリアルタイム更新
- ✅ ズーム/パン機能
- ✅ マルチトラック対応
- ✅ キーボードショートカット（JKL編集など）
- ✅ プレビュー再生（Web Audio API使用）

### 2. ビデオプレビューコンポーネント
```typescript
interface VideoPreviewProps {
  videoUrl: string;
  currentTime: number;
  markers: TimeRange[];
}
```

**機能：**
- ✅ インラインビデオプレビュー
- ✅ フレーム単位のシーク
- ✅ マーカー表示
- ✅ A/Bループ再生

## 実装手順

### Step 1: 開発環境のセットアップ
```bash
# プロジェクトディレクトリ作成
cd ui/custom_components
npx create-react-app timeline-editor-react --template typescript
cd timeline-editor-react

# Streamlitコンポーネントライブラリをインストール
npm install streamlit-component-lib
npm install @types/streamlit-component-lib
```

### Step 2: React コンポーネントの実装
```typescript
// src/TimelineEditor.tsx
import React, { useEffect, useRef, useState } from 'react';
import { Streamlit, ComponentProps } from "streamlit-component-lib";

interface Clip {
  id: string;
  startTime: number;
  endTime: number;
  waveform: number[];
}

const TimelineEditor: React.FC<ComponentProps> = (props) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [clips, setClips] = useState<Clip[]>(props.args.clips || []);
  const [selectedClip, setSelectedClip] = useState<number>(-1);
  const [isDragging, setIsDragging] = useState(false);

  // Canvas描画ロジック
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 波形描画
    drawWaveforms(ctx, clips);
  }, [clips]);

  // ドラッグ処理
  const handleMouseDown = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    const x = e.clientX - rect.left;
    // クリップ境界の検出ロジック
    // ...
    setIsDragging(true);
  };

  // Streamlitへのデータ送信
  const updateClips = (newClips: Clip[]) => {
    setClips(newClips);
    Streamlit.setComponentValue(newClips);
  };

  return (
    <div style={{ padding: '20px' }}>
      <canvas
        ref={canvasRef}
        width={800}
        height={200}
        onMouseDown={handleMouseDown}
        style={{ border: '1px solid #ddd', cursor: 'pointer' }}
      />
      {/* 詳細編集UI */}
      {selectedClip >= 0 && (
        <div style={{ marginTop: '20px' }}>
          <h3>クリップ {selectedClip + 1} の編集</h3>
          {/* 数値入力フィールドなど */}
        </div>
      )}
    </div>
  );
};

export default TimelineEditor;
```

### Step 3: Pythonラッパーの実装
```python
# ui/custom_components/timeline_editor_react/__init__.py
import streamlit.components.v1 as components
import os

# 開発時
_DEVELOP_MODE = os.getenv("STREAMLIT_COMPONENT_DEV_MODE", False)

if _DEVELOP_MODE:
    _component_func = components.declare_component(
        "timeline_editor_react",
        url="http://localhost:3001",  # React開発サーバー
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend/build")
    _component_func = components.declare_component(
        "timeline_editor_react", 
        path=build_dir
    )

def timeline_editor_react(clips, key=None):
    """
    React製タイムラインエディタ
    
    Args:
        clips: クリップデータのリスト
        key: コンポーネントのキー
    
    Returns:
        編集されたクリップデータ
    """
    component_value = _component_func(
        clips=clips,
        key=key,
        default=clips
    )
    return component_value
```

### Step 4: TextffCutへの統合
```python
# main.py での使用例
if st.session_state.get("use_advanced_editor", False):
    from ui.custom_components.timeline_editor_react import timeline_editor_react
    
    # React製エディタを使用
    edited_clips = timeline_editor_react(
        clips=clips_data,
        key="timeline_editor"
    )
    
    if edited_clips:
        # 編集結果を処理
        adjusted_ranges = [(c["startTime"], c["endTime"]) for c in edited_clips]
else:
    # 既存のシンプル版を使用
    from ui.timeline_editor_simple import render_timeline_editor_simple
    render_timeline_editor_simple(time_ranges, transcription, video_path)
```

## メリット

1. **高度なインタラクション**
   - ドラッグ＆ドロップ
   - リアルタイム更新
   - スムーズなアニメーション

2. **再利用性**
   - 他のプロジェクトでも使用可能
   - npmパッケージとして公開可能

3. **保守性**
   - TypeScriptによる型安全性
   - Reactのエコシステム活用
   - テスト容易性

## デメリット

1. **複雑性の増加**
   - ビルドプロセスが必要
   - Node.js環境が必要
   - デバッグが複雑

2. **配布サイズ**
   - Reactバンドルで数MB増加
   - 初回ロード時間の増加

## 推奨される実装戦略

### Phase 1: 現状維持（完了）
- シンプル版で基本機能を確立 ✅

### Phase 2: プロトタイプ作成
- 1つの高度な機能（例：波形ドラッグ）のみ実装
- 技術検証とユーザーフィードバック収集

### Phase 3: 段階的移行
- 設定で切り替え可能に
- 高度な編集が必要なユーザーのみ有効化

### Phase 4: 完全統合
- すべての編集機能をReact版に移行
- レガシー版を削除

## 開発時間の見積もり

- プロトタイプ: 2-3日
- 基本機能: 1週間
- 完全な機能: 2-3週間

## 結論

Streamlit Custom Components（React + TypeScript）の導入は技術的に可能で、TextffCutの価値を大幅に向上させる可能性があります。ただし、現在のシンプル版が安定して動作しているため、段階的な導入が推奨されます。