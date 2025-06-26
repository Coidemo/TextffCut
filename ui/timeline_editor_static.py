"""
静的コンポーネントを使用したタイムライン編集UI
HTMLとJavaScriptを直接埋め込むシンプルな実装
"""
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
import json

from core.waveform_processor import WaveformProcessor
from utils.logging import get_logger

logger = get_logger(__name__)


def render_timeline_editor_static(time_ranges: list[tuple[float, float]], transcription_result: Any, video_path: str) -> None:
    """
    静的コンポーネントを使用したタイムライン編集UI
    
    Args:
        time_ranges: 編集対象の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
    """
    st.markdown("### 📝 インタラクティブ・タイムライン編集")
    
    # 波形データの準備
    if "timeline_waveforms" not in st.session_state:
        with st.spinner("波形データを抽出中..."):
            processor = WaveformProcessor()
            waveform_data = processor.extract_waveforms_for_clips(
                video_path,
                time_ranges,
                samples_per_clip=200
            )
            st.session_state.timeline_waveforms = waveform_data
    else:
        waveform_data = st.session_state.timeline_waveforms
    
    # クリップデータの準備
    clips_data = []
    for i, ((start, end), waveform) in enumerate(zip(time_ranges, waveform_data)):
        clips_data.append({
            "id": f"clip_{i}",
            "start_time": start,
            "end_time": end,
            "samples": waveform.samples if waveform else []
        })
    
    # HTMLコンテンツを生成
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .timeline-container {{
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
            }}
            #timeline-canvas {{
                border: 1px solid #ddd;
                cursor: pointer;
                display: block;
                margin: 0 auto;
            }}
            #apply-button {{
                background-color: #4ECDC4;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                margin-top: 10px;
            }}
            #apply-button:hover {{
                background-color: #45b7aa;
            }}
            #clip-info {{
                background-color: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="timeline-container">
            <canvas id="timeline-canvas" width="800" height="200"></canvas>
            <div id="clip-info">
                <p>クリップを選択してください</p>
            </div>
            <button id="apply-button">変更を適用</button>
        </div>
        
        <script>
            // クリップデータをJavaScriptに渡す
            const clipsData = {json.dumps(clips_data)};
            let selectedClipIndex = -1;
            let canvas = null;
            let ctx = null;
            
            // 初期化
            document.addEventListener('DOMContentLoaded', () => {{
                canvas = document.getElementById('timeline-canvas');
                ctx = canvas.getContext('2d');
                
                canvas.addEventListener('click', handleCanvasClick);
                document.getElementById('apply-button').onclick = handleApplyChanges;
                
                drawTimeline();
                
                // 初期化時にもテキストエリアを更新
                setTimeout(() => {{
                    updateTextArea();
                    console.log('Initial update of textarea');
                }}, 500);
            }});
            
            // タイムラインを描画
            function drawTimeline() {{
                if (!canvas || !ctx) return;
                
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = "#f0f0f0";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                
                if (clipsData.length === 0) {{
                    ctx.fillStyle = "#333";
                    ctx.font = "16px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText("クリップデータがありません", canvas.width / 2, canvas.height / 2);
                    return;
                }}
                
                const padding = 10;
                const totalWidth = canvas.width - 2 * padding;
                const clipHeight = 120;
                const yOffset = 40;
                
                let currentX = padding;
                const totalDuration = clipsData[clipsData.length - 1].end_time;
                
                clipsData.forEach((clip, index) => {{
                    const duration = clip.end_time - clip.start_time;
                    const clipWidth = (duration / totalDuration) * totalWidth;
                    
                    // クリップの背景
                    ctx.fillStyle = index === selectedClipIndex ? "#4ECDC4" : "#95a5a6";
                    ctx.fillRect(currentX, yOffset, clipWidth, clipHeight);
                    
                    // 波形を描画
                    drawWaveform(currentX, yOffset, clipWidth, clipHeight, clip.samples || []);
                    
                    // クリップ番号
                    ctx.fillStyle = "white";
                    ctx.font = "14px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText(`${{index + 1}}`, currentX + clipWidth / 2, yOffset + clipHeight / 2 + 5);
                    
                    // 時間情報
                    ctx.font = "10px Arial";
                    ctx.fillText(
                        `${{formatTime(clip.start_time)}} - ${{formatTime(clip.end_time)}}`,
                        currentX + clipWidth / 2,
                        yOffset + clipHeight + 15
                    );
                    
                    clip._x = currentX;
                    clip._width = clipWidth;
                    
                    currentX += clipWidth + 5;
                }});
            }}
            
            // 波形を描画
            function drawWaveform(x, y, width, height, samples) {{
                if (!samples || samples.length === 0) {{
                    samples = [];
                    for (let i = 0; i < 100; i++) {{
                        samples.push(Math.random() * 0.8 - 0.4);
                    }}
                }}
                
                ctx.strokeStyle = "rgba(255, 255, 255, 0.8)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                
                const centerY = y + height / 2;
                const amplitude = height * 0.4;
                
                for (let i = 0; i < samples.length; i++) {{
                    const sampleX = x + (i / samples.length) * width;
                    const sampleY = centerY + samples[i] * amplitude;
                    
                    if (i === 0) {{
                        ctx.moveTo(sampleX, sampleY);
                    }} else {{
                        ctx.lineTo(sampleX, sampleY);
                    }}
                }}
                
                ctx.stroke();
            }}
            
            // クリックハンドラー
            function handleCanvasClick(event) {{
                const rect = canvas.getBoundingClientRect();
                const x = event.clientX - rect.left;
                
                let clickedIndex = -1;
                for (let i = 0; i < clipsData.length; i++) {{
                    const clip = clipsData[i];
                    if (x >= clip._x && x <= clip._x + clip._width) {{
                        clickedIndex = i;
                        break;
                    }}
                }}
                
                if (clickedIndex !== -1) {{
                    selectedClipIndex = clickedIndex;
                    drawTimeline();
                    updateClipInfo();
                }}
            }}
            
            // クリップ情報を更新
            function updateClipInfo() {{
                const infoDiv = document.getElementById('clip-info');
                if (selectedClipIndex === -1) {{
                    infoDiv.innerHTML = "<p>クリップを選択してください</p>";
                    return;
                }}
                
                const clip = clipsData[selectedClipIndex];
                infoDiv.innerHTML = `
                    <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0;">🎥 クリップ ${{selectedClipIndex + 1}}</h4>
                        <div style="display: flex; gap: 20px; margin-bottom: 10px;">
                            <div>
                                <label style="font-weight: bold; display: block; margin-bottom: 5px;">開始時間</label>
                                <input type="text" id="start-time-input" value="${{formatTimeWithMs(clip.start_time)}}" 
                                    style="padding: 5px; border: 1px solid #ddd; border-radius: 4px; width: 120px;"
                                    onchange="updateClipTime('start', this.value)">
                                <div style="margin-top: 5px;">
                                    <button onclick="adjustTime('start', -1)" style="padding: 2px 8px; margin: 2px;">-1s</button>
                                    <button onclick="adjustTime('start', -0.1)" style="padding: 2px 8px; margin: 2px;">-0.1s</button>
                                    <button onclick="adjustTime('start', 0.1)" style="padding: 2px 8px; margin: 2px;">+0.1s</button>
                                    <button onclick="adjustTime('start', 1)" style="padding: 2px 8px; margin: 2px;">+1s</button>
                                </div>
                            </div>
                            <div>
                                <label style="font-weight: bold; display: block; margin-bottom: 5px;">終了時間</label>
                                <input type="text" id="end-time-input" value="${{formatTimeWithMs(clip.end_time)}}" 
                                    style="padding: 5px; border: 1px solid #ddd; border-radius: 4px; width: 120px;"
                                    onchange="updateClipTime('end', this.value)">
                                <div style="margin-top: 5px;">
                                    <button onclick="adjustTime('end', -1)" style="padding: 2px 8px; margin: 2px;">-1s</button>
                                    <button onclick="adjustTime('end', -0.1)" style="padding: 2px 8px; margin: 2px;">-0.1s</button>
                                    <button onclick="adjustTime('end', 0.1)" style="padding: 2px 8px; margin: 2px;">+0.1s</button>
                                    <button onclick="adjustTime('end', 1)" style="padding: 2px 8px; margin: 2px;">+1s</button>
                                </div>
                            </div>
                        </div>
                        <p style="color: #666; margin: 5px 0;">長さ: ${{formatTime(clip.end_time - clip.start_time)}}</p>
                        <p style="color: #888; font-size: 0.9em; margin: 5px 0;">💡 ヒント: 数値を直接入力するか、ボタンで調整できます</p>
                    </div>
                `;
            }}
            
            // 変更を適用
            function handleApplyChanges() {{
                // テキストエリアを更新
                updateTextArea();
                
                // ボタンのテキストを変更してフィードバック
                const applyBtn = document.getElementById('apply-button');
                if (applyBtn) {{
                    applyBtn.textContent = '✅ 変更済み';
                    applyBtn.style.backgroundColor = '#2ecc71';
                    
                    // メッセージを表示
                    const infoDiv = document.getElementById('clip-info');
                    if (infoDiv) {{
                        infoDiv.innerHTML += '<div style="background-color: #d4edda; color: #155724; padding: 10px; margin-top: 10px; border-radius: 4px;">✅ 変更が適用されました。<br>右側の「編集完了」ボタンを押してください。</div>';
                    }}
                }}
            }}
            
            // ユーティリティ関数
            function formatTime(seconds) {{
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                return `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
            }}
            
            // ミリ秒付き時間フォーマット
            function formatTimeWithMs(seconds) {{
                const mins = Math.floor(seconds / 60);
                const secs = seconds % 60;
                return `${{mins}}:${{secs.toFixed(3).padStart(6, '0')}}`;
            }}
            
            // 時間文字列を秒数に変換
            function parseTime(timeStr) {{
                const parts = timeStr.split(':');
                if (parts.length !== 2) return null;
                const mins = parseInt(parts[0], 10);
                const secs = parseFloat(parts[1]);
                if (isNaN(mins) || isNaN(secs)) return null;
                return mins * 60 + secs;
            }}
            
            // 時間調整関数
            function adjustTime(type, delta) {{
                if (selectedClipIndex === -1) return;
                
                const clip = clipsData[selectedClipIndex];
                if (type === 'start') {{
                    const newTime = Math.max(0, clip.start_time + delta);
                    // 終了時間を超えないように
                    if (newTime < clip.end_time - 0.1) {{
                        clip.start_time = newTime;
                    }}
                }} else {{
                    const newTime = clip.end_time + delta;
                    // 開始時間より後で、次のクリップより前に
                    const maxTime = selectedClipIndex < clipsData.length - 1 
                        ? clipsData[selectedClipIndex + 1].start_time 
                        : Infinity;
                    if (newTime > clip.start_time + 0.1 && newTime <= maxTime) {{
                        clip.end_time = newTime;
                    }}
                }}
                
                drawTimeline();
                updateClipInfo();
                updateTextArea(); // テキストエリアを更新
            }}
            
            // 時間直接入力の処理
            function updateClipTime(type, timeStr) {{
                if (selectedClipIndex === -1) return;
                
                const newTime = parseTime(timeStr);
                if (newTime === null) {{
                    alert('正しい時間形式で入力してください (例: 1:23.456)');
                    updateClipInfo(); // 元の値に戻す
                    return;
                }}
                
                const clip = clipsData[selectedClipIndex];
                if (type === 'start') {{
                    if (newTime < clip.end_time - 0.1 && newTime >= 0) {{
                        clip.start_time = newTime;
                    }} else {{
                        alert('開始時間は終了時間より前である必要があります');
                        updateClipInfo();
                        return;
                    }}
                }} else {{
                    const maxTime = selectedClipIndex < clipsData.length - 1 
                        ? clipsData[selectedClipIndex + 1].start_time 
                        : Infinity;
                    if (newTime > clip.start_time + 0.1 && newTime <= maxTime) {{
                        clip.end_time = newTime;
                    }} else {{
                        alert('終了時間は開始時間より後で、次のクリップより前である必要があります');
                        updateClipInfo();
                        return;
                    }}
                }}
                
                drawTimeline();
                updateClipInfo();
                updateTextArea(); // テキストエリアを更新
            }}
            
            // テキストエリアに変更を反映
            function updateTextArea() {{
                try {{
                    const textArea = window.parent.document.querySelector('textarea[aria-label="編集結果（JSON）"]');
                    if (textArea) {{
                        const editedRanges = clipsData.map(clip => ({{
                            start_time: clip.start_time,
                            end_time: clip.end_time
                        }}));
                        const jsonStr = JSON.stringify(editedRanges);
                        console.log('Updating textarea with:', jsonStr);
                        textArea.value = jsonStr;
                        textArea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        
                        // デバッグ用：更新後の値を確認
                        setTimeout(() => {{
                            console.log('Textarea value after update:', textArea.value);
                        }}, 100);
                    }} else {{
                        console.error('Textarea not found');
                    }}
                }} catch (e) {{
                    console.error('Failed to update text area:', e);
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    # HTMLコンポーネントを表示
    components.html(html_content, height=500, scrolling=False)
    
    # JavaScriptからの変更を受け取るための隠し入力フィールド
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        # 編集結果を保存する隠しテキストエリア
        initial_json = json.dumps([{"start_time": s, "end_time": e} for s, e in time_ranges])
        edited_ranges_json = st.text_area(
            "編集結果（JSON）", 
            value=initial_json,
            height=100,
            key="edited_ranges_json",
            help="JavaScript側で編集された時間範囲がここに反映されます"
        )
        
        # デバッグ用：初期値と現在値を比較
        if edited_ranges_json != initial_json:
            st.success("✅ 時間範囲が編集されました")
    
    with col2:
        if st.button("✅ 編集完了", key="timeline_apply_changes", use_container_width=True, type="primary"):
            # セッション状態から最新の値を取得（重要！）
            current_json = st.session_state.get("edited_ranges_json", edited_ranges_json)
            
            # デバッグ表示
            st.info("🔍 値の確認")
            col_debug1, col_debug2 = st.columns(2)
            with col_debug1:
                st.caption("初期値")
                initial_data = [{"start_time": s, "end_time": e} for s, e in time_ranges[:2]]
                st.code(json.dumps(initial_data, indent=2))
            with col_debug2:
                st.caption("現在値（セッション状態）")
                try:
                    current_data = json.loads(current_json)[:2]
                    st.code(json.dumps(current_data, indent=2))
                except:
                    st.code(current_json[:200])
            
            try:
                # セッション状態の値をパース
                edited_data = json.loads(current_json)
                adjusted_ranges = [(item["start_time"], item["end_time"]) for item in edited_data]
                
                # 保存前に値を確認
                st.success(f"✅ 保存する時間範囲: {len(adjusted_ranges)}クリップ")
                for i, (start, end) in enumerate(adjusted_ranges[:3]):
                    st.write(f"  クリップ{i+1}: {start:.1f}秒 - {end:.1f}秒 (長さ: {end-start:.1f}秒)")
                
                # セッション状態に保存
                st.session_state.adjusted_time_ranges = adjusted_ranges
                st.session_state.timeline_editing_completed = True
                if "timeline_waveforms" in st.session_state:
                    del st.session_state.timeline_waveforms
                
                # 少し待ってからrerun
                import time
                time.sleep(0.5)
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"編集データの形式が正しくありません: {str(e)}")
                st.write("エラーのJSONデータ:", current_json)
                st.write("エラー詳細:", str(e))
    
    with col3:
        if st.button("✖ キャンセル", key="timeline_cancel", use_container_width=True):
            st.session_state.timeline_editing_cancelled = True
            if "timeline_waveforms" in st.session_state:
                del st.session_state.timeline_waveforms
            st.rerun()
    
    # デバッグ情報を表示（フラグメント化して動的更新を可能に）
    @st.fragment
    def show_debug_info():
        with st.expander("デバッグ情報", expanded=False):
            # 最新の値を取得
            current_json = st.session_state.get("edited_ranges_json", edited_ranges_json)
            st.code(current_json, language="json")
            st.caption("👆 JavaScript側から更新された編集結果がここに表示されます")
            
            # 編集されたデータをパース
            try:
                edited_data = json.loads(current_json)
                for i, item in enumerate(edited_data):
                    st.text(f"クリップ{i+1}: {item['start_time']:.3f}秒 - {item['end_time']:.3f}秒 (長さ: {item['end_time'] - item['start_time']:.3f}秒)")
            except:
                st.error("JSONのパースに失敗しました")
    
    # デバッグ情報を表示
    show_debug_info()