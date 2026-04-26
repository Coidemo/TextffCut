"""`textffcut send` サブコマンド。

DaVinci Resolve の現在開いているビンに、TextffCut が生成した FCPXML と SRT を
取り込む。timeline 名は `00_MMDD_Clip{NN}` (NN は対象ビン内の既存 max+1)、
素材用 SE track は自動でミュートされる。

事前準備:
  - DaVinci Resolve 20 を起動 + プロジェクトを開く
  - Preferences > System > General > External scripting using: Local
  - Media Pool で配置先のビンをクリックして開く

例:
  textffcut send videos/20260210_xxx_TextffCut/fcpxml/02_yyy.fcpxml
  textffcut send path/to/clip.fcpxml --mmdd 0210
  textffcut send clip.fcpxml --text-plus  # SRT を Text+ クリップに自動変換

--text-plus 利用時の追加事前準備:
  - Media Pool root に "TextffCut" ビンを作成
  - その中に "Caption_Default" という Fusion Title (Text+) テンプレートを配置
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textffcut send",
        description=(
            "DaVinci Resolve の現在開いているビンに、TextffCut が生成した FCPXML + SRT を取り込む。\n"
            "timeline 名は `00_MMDD_Clip{NN}` (NN はビン内既存 max+1)。素材用 SE は自動 mute。\n\n"
            "事前準備:\n"
            "  - DaVinci Resolve 20 を起動 + プロジェクトを開く\n"
            "  - Preferences > System > General > External scripting using: Local\n"
            "  - Media Pool で配置先のビンをクリックして開く\n\n"
            "例:\n"
            "  textffcut send videos/20260210_xxx_TextffCut/fcpxml/02_yyy.fcpxml\n"
            "  textffcut send clip.fcpxml --mmdd 0210\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("fcpxml", type=Path, help="送信する FCPXML ファイルパス")
    parser.add_argument(
        "--srt",
        type=Path,
        default=None,
        help="SRT ファイルパス (省略時は FCPXML と同名の .srt を自動検出)",
    )
    parser.add_argument(
        "--mmdd",
        default=None,
        help="連番計算用の月日 (例: 0210)。省略時は動画フォルダ名 YYYYMMDD_xxx_TextffCut から自動抽出",
    )
    parser.add_argument(
        "--text-plus",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "SRT 取り込み後に字幕を Fusion Text+ クリップへ自動変換 (default: 有効)。"
            "Media Pool に TextffCut ビンと Caption_Default テンプレートが無ければ自動スキップ"
        ),
    )
    parser.add_argument(
        "--text-plus-bin",
        default="TextffCut",
        help="Text+ テンプレートを格納したビン名 (default: TextffCut)",
    )
    parser.add_argument(
        "--text-plus-template",
        default="Caption_Default",
        help="Text+ テンプレート名 (default: Caption_Default)",
    )
    parser.add_argument(
        "--text-plus-max-fill-frames",
        type=int,
        default=None,
        help=(
            "Fill Gaps で埋める字幕間 gap の最大フレーム数 (default: 9999 ≈ 5.5min @30fps、"
            "実用上ほぼ無制限). 小さくすると短い gap だけ埋める."
        ),
    )
    return parser


def run_send(argv: list[str]) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    from infrastructure.davinci_resolve import (
        TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES,
        ResolveError,
        send_clip_to_resolve,
    )

    max_fill = (
        args.text_plus_max_fill_frames
        if args.text_plus_max_fill_frames is not None
        else TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES
    )
    try:
        result = send_clip_to_resolve(
            args.fcpxml,
            srt_path=args.srt,
            mmdd=args.mmdd,
            text_plus=args.text_plus,
            text_plus_bin=args.text_plus_bin,
            text_plus_template=args.text_plus_template,
            text_plus_max_fill_frames=max_fill,
        )
    except ResolveError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Bin {result.bin_name!r} に {result.timeline_name} を作成")
    if result.srt_imported:
        print(f"  字幕トラック追加: OK")
    else:
        print(f"  字幕: スキップ (SRT 未検出 or import 失敗)")
    if result.se_muted:
        muted = ", ".join(f"A{i}" for i in result.se_muted)
        print(f"  素材用 SE ミュート: {muted}")
    if result.se_kept:
        kept = ", ".join(f"A{i}" for i in result.se_kept)
        print(f"  AI 配置 SE 維持: {kept}")
    if result.text_plus is not None:
        tp = result.text_plus
        suffix = " (subtitle 無効化済)" if tp.subtitle_disabled else ""
        if tp.video_track == 0:
            print(f"  Text+ 変換: 全件失敗 (空 track は削除){suffix}")
        else:
            print(
                f"  Text+ 変換: V{tp.video_track} に "
                f"{tp.success}/{tp.success + tp.failed} 件配置{suffix}"
            )
    elif args.text_plus:
        print("  Text+ 変換: スキップ (詳細はログ参照)")
