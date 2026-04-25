"""字幕エディタ section のレンダラ (Streamlit 側).

**タイミング調整のみ**: 改行・entry 区切りの編集が可能。
文字の追加・削除・変更は禁止（char_times とマッピング不可能になるため）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import streamlit as st

from ui.subtitle_editor.widget import (
    MAX_CHARS,
    assign_timing_from_structure,
    entries_to_text,
    flatten_text,
    parse_edited_text,
    render_preview_html,
    validate_edit,
)
from use_cases.ai.srt_edit_log import (
    SRTEntry,
    append_edit_log,
    load_edit_log,
    parse_srt,
    reconstruct_entry_timing,
    write_srt,
)
from use_cases.ai.srt_meta_backfill import ensure_srt_meta

logger = logging.getLogger(__name__)


def _find_textffcut_dirs(videos_root: Path) -> list[Path]:
    if not videos_root.exists():
        return []
    return sorted([p for p in videos_root.iterdir() if p.is_dir() and p.name.endswith("_TextffCut")])


def _list_srt_files(base_dir: Path) -> list[Path]:
    fcpxml_dir = base_dir / "fcpxml"
    if not fcpxml_dir.exists():
        return []
    return sorted(p for p in fcpxml_dir.glob("*.srt") if not p.name.endswith(".bak") and re.match(r"^\d+_", p.stem))


def _handle_save(
    base_dir: Path,
    srt_path: Path,
    original: list[SRTEntry],
    edited: list[SRTEntry],
    clip_id: str,
    *,
    meta: tuple[str, list[tuple[float, float]]] | None = None,
    algorithm_version: str = "v2_fix_f",
    edit_duration_sec: float | None = None,
) -> None:
    """SRT 上書き + edit log 追記.

    meta が渡された場合、char_times と full_text を log に保存して LoRA 訓練時の
    timing mapping を可能にする (docstring 通りの挙動).
    """
    write_srt(edited, srt_path)
    if meta is not None:
        meta_full_text, meta_char_times = meta
    else:
        # meta 無し (近似モード): canonical flat (全空白除去 + NFC) で構築.
        # meta 経路と semantics を揃えて、log 消費側が経路による揺れで
        # 困らないようにする.
        meta_full_text = flatten_text("".join(e.text for e in original))
        meta_char_times = None
    log_path = append_edit_log(
        base_dir=base_dir,
        clip_id=clip_id,
        original=original,
        edited=edited,
        algorithm_version=algorithm_version,
        full_text=meta_full_text,
        char_times=meta_char_times,
        edit_duration_sec=edit_duration_sec,
    )
    st.success(f"✓ 保存しました: {srt_path.name}  (ログ: {log_path.name})")


def render_subtitle_editor_section(container: Any, videos_root: str = "videos") -> None:  # noqa: ANN401
    """字幕編集 section."""
    import streamlit.components.v1 as components

    videos_root_path = Path(videos_root)
    container.subheader("✏️ 字幕編集")

    dirs = _find_textffcut_dirs(videos_root_path)
    if not dirs:
        container.info(f"{videos_root} に処理済み動画フォルダがまだありません。")
        return

    dir_names = [d.name.removesuffix("_TextffCut") for d in dirs]
    sel_dir_idx = container.selectbox(
        "動画フォルダ",
        range(len(dirs)),
        format_func=lambda i: dir_names[i],
        key="subtitle_editor_dir_idx",
    )
    base_dir = dirs[sel_dir_idx]

    srt_files = _list_srt_files(base_dir)
    if not srt_files:
        container.info("このフォルダに SRT ファイルが見つかりません。")
        return
    sel_srt_idx = container.selectbox(
        "クリップ",
        range(len(srt_files)),
        format_func=lambda i: srt_files[i].stem,
        key="subtitle_editor_srt_idx",
    )
    srt_path = srt_files[sel_srt_idx]
    clip_id = srt_path.stem

    try:
        original_entries = parse_srt(srt_path)
    except Exception as e:
        container.error(f"SRT 読み込み失敗: {e}")
        return
    if not original_entries:
        container.warning("SRT が空です。")
        return

    # テキストエリア
    ta_cache_key = f"_srt_cache__{base_dir.name}__{srt_path.stem}"
    reset_flag_key = f"_reset_req__{ta_cache_key}"
    original_text = entries_to_text(original_entries)

    # リセット要求があれば cache + widget state の両方をクリア
    # (widget は key= 指定のため session_state[widget_key] を直接持つので
    #  ta_cache_key だけ消しても widget 側は古い値を保持し続ける)
    widget_key = f"widget_{ta_cache_key}"
    if st.session_state.pop(reset_flag_key, False):
        st.session_state.pop(ta_cache_key, None)
        st.session_state.pop(widget_key, None)

    default_text = st.session_state.get(ta_cache_key, original_text)

    edited_text = container.text_area(
        "字幕テキスト（空行で entry 区切り・改行で行区切り）",
        value=default_text,
        height=340,
        help=f"**改行・空行の編集のみ**可能。文字の追加・削除・変更は不可。1 行最大 {MAX_CHARS} 字。",
        key=widget_key,
    )
    st.session_state[ta_cache_key] = edited_text
    ta_key = ta_cache_key

    v = validate_edit(original_text, edited_text)

    if not v.ok:
        container.error(f"⚠️ {v.error_msg}")
        # デバッグ: 差分を表示
        with container.expander("🔍 差分の詳細 (デバッグ)"):
            import difflib

            o_lines = original_text.split("\n")
            e_lines = edited_text.split("\n")
            diff = list(difflib.unified_diff(o_lines, e_lines, lineterm="", n=2))
            if diff:
                container.code("\n".join(diff[:40]), language="diff")
            else:
                container.write("差分なし (unified_diff は空) - NFC 正規化等の非表示文字差の可能性")
            container.caption(f"original 長さ: {len(original_text)}, edited 長さ: {len(edited_text)}")

    # parse & timing 計算
    # 1. meta (char_times) があれば音響正確な timing 復元
    # 2. 無ければ文字数比での近似
    parsed_blocks = parse_edited_text(edited_text)
    edited_entries: list[SRTEntry] = []
    timing_source = ""
    meta = ensure_srt_meta(base_dir, srt_path) if v.ok else None
    if v.ok and parsed_blocks:
        if meta is not None:
            full_text, char_times = meta
            reconstructed = reconstruct_entry_timing(parsed_blocks, full_text, char_times)
            if reconstructed is not None:
                edited_entries = reconstructed
                timing_source = "meta"
        if not edited_entries:
            edited_entries = assign_timing_from_structure(parsed_blocks, original_entries)
            timing_source = "approx"

    # stats
    if edited_entries:
        total = len(edited_entries)
        one_line = sum(1 for e in edited_entries if "\n" not in e.text)
        over = sum(1 for e in edited_entries if any(len(ln) > MAX_CHARS for ln in e.lines))
        cols = container.columns(4)
        cols[0].metric("entries", total)
        cols[1].metric("1行", one_line)
        cols[2].metric(
            f"{MAX_CHARS}字超過",
            over,
            delta=None if over == 0 else f"⚠ {over}",
        )
        timing_label = "🎯 音響同期" if timing_source == "meta" else "📏 近似配分"
        cols[3].metric("timing", timing_label)

        # timeline 可視化
        components.html(render_preview_html(edited_entries), height=56, scrolling=False)

    # 操作ボタン
    btn_cols = container.columns([1, 1, 1, 2])
    if btn_cols[0].button("↺ リセット", key=f"reset_{ta_key}"):
        st.session_state[reset_flag_key] = True
        st.rerun()

    save_disabled = (not v.ok) or (not edited_entries)
    if btn_cols[1].button(
        "💾 保存",
        key=f"save_{ta_key}",
        disabled=save_disabled,
        type="primary",
    ):
        try:
            _handle_save(
                base_dir=base_dir,
                srt_path=srt_path,
                original=original_entries,
                edited=edited_entries,
                clip_id=clip_id,
                meta=meta,
            )
            # 保存成功: session_state をリセットフラグで clear して
            # 次 rerun で disk から再ロードさせる (mode 切替時の stale データ防止)
            st.session_state[reset_flag_key] = True
            st.rerun()
        except Exception as e:
            container.error(f"保存処理失敗: {e}")
            logger.exception("SRT 保存エラー")

    # DaVinci Resolve に送信
    fcpxml_path = srt_path.with_suffix(".fcpxml")
    send_disabled = save_disabled or (not fcpxml_path.exists())
    if btn_cols[2].button(
        "📺 DaVinciへ送信",
        key=f"send_{ta_key}",
        disabled=send_disabled,
        help=(
            "DaVinci Resolve の現在開いているビンに timeline + 字幕を取り込みます。\n"
            "保存していない編集内容は反映されません (先に '💾 保存' を押してください)。"
        ),
    ):
        try:
            from infrastructure.davinci_resolve import ResolveError, send_clip_to_resolve

            result = send_clip_to_resolve(fcpxml_path)
            msg_lines = [
                f"✓ Bin {result['bin_name']!r} に {result['timeline_name']} を作成",
                f"  字幕: {'OK' if result['srt_imported'] else 'スキップ'}",
            ]
            if result["se_muted"]:
                muted = ", ".join(f"A{i}" for i in result["se_muted"])
                msg_lines.append(f"  素材用 SE ミュート: {muted}")
            container.success("\n".join(msg_lines))
        except ResolveError as e:
            container.error(f"Resolve 送信失敗:\n{e}")
            logger.warning(f"DaVinci 送信失敗: {e}")
        except Exception as e:
            container.error(f"予期しないエラー: {e}")
            logger.exception("DaVinci 送信エラー")

    # 過去の編集ログ概要
    logs = load_edit_log(base_dir)
    if logs:
        with container.expander(f"📋 過去の編集ログ ({len(logs)} 件)"):
            container.dataframe(
                [
                    {
                        "timestamp": L.get("timestamp", ""),
                        "clip": L.get("clip_id", ""),
                        "mode": L.get("algorithm_version", "").split("_")[-1],
                        "entries": f"{L.get('diff_summary', {}).get('entries_before', '?')}"
                        f"→{L.get('diff_summary', {}).get('entries_after', '?')}",
                        "edit_time": L.get("edit_duration_sec"),
                    }
                    for L in logs[-20:]
                ],
                use_container_width=True,
            )
