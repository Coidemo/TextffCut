"""
textffcut suggest サブコマンド

文字起こし → AI切り抜き候補生成 → FCPXML出力を一気通貫で実行する。
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

# use_cases/ai/ 配下のlogger.info()をCLI出力に表示する
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
# 候補生成のログのみINFOレベルで表示
for _mod in (
    "use_cases.ai.brute_force_clip_generator",
    "use_cases.ai.suggest_and_export",
):
    logging.getLogger(_mod).setLevel(logging.INFO)


def build_suggest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textffcut clip",
        description="AI自動切り抜き — 話題検出→最適カット→FCPXML出力",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE_OR_DIR",
        help="処理する動画ファイルまたはフォルダのパス（省略時: ./videos/）",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="large-v3",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        metavar="MODEL",
        help="文字起こしモデル（デフォルト: large-v3）",
    )
    parser.add_argument(
        "--ai-model",
        default="gpt-4.1-mini",
        choices=["gpt-4.1-mini", "gpt-4.1"],
        metavar="AI_MODEL",
        help="AIモデル（デフォルト: gpt-4.1-mini）",
    )
    parser.add_argument(
        "--quality-model",
        default="gpt-4.1",
        choices=["gpt-4.1-mini", "gpt-4.1"],
        metavar="QUALITY_MODEL",
        help=(
            "品質評価用 AI モデル（デフォルト: gpt-4.1）。"
            "ai-model と同じ値なら override 無効（全 sub-step が ai-model）。"
        ),
    )
    parser.add_argument(
        "--num",
        type=int,
        default=5,
        help="生成する候補数（デフォルト: 5）",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=30,
        help="最小秒数（デフォルト: 30）",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=60,
        help="最大秒数（デフォルト: 60）",
    )
    parser.add_argument(
        "--no-srt",
        dest="generate_srt",
        action="store_false",
        default=True,
        help="SRT字幕ファイルを生成しない（デフォルト: 生成する）",
    )
    parser.add_argument(
        "--srt-max-chars",
        type=int,
        default=11,
        help="SRT字幕の1行あたり最大文字数（デフォルト: 11）",
    )
    parser.add_argument(
        "--srt-max-lines",
        type=int,
        default=2,
        help="SRT字幕の最大行数（デフォルト: 2）",
    )
    parser.add_argument(
        "--no-silence-removal",
        dest="remove_silence",
        action="store_false",
        default=True,
        help="無音削除を無効にする（デフォルト: 有効）",
    )

    def _speed_type(value: str) -> float:
        f = float(value)
        if not (0.5 <= f <= 2.0):
            raise argparse.ArgumentTypeError(f"0.5〜2.0の範囲で指定してください: {value}")
        return f

    parser.add_argument(
        "--speed",
        type=_speed_type,
        default=1.0,
        help="再生速度（0.5〜2.0、デフォルト: 1.0、例: 1.2で1.2倍速）",
    )

    def _zoom_type(value: str) -> int:
        i = int(value)
        if not (10 <= i <= 500):
            raise argparse.ArgumentTypeError(f"10〜500の範囲で指定してください: {value}")
        return i

    parser.add_argument(
        "--zoom",
        type=_zoom_type,
        default=100,
        metavar="PERCENT",
        help="ズーム（10〜500%%、デフォルト: 100%%、例: 200で2倍拡大）",
    )
    parser.add_argument(
        "--anchor",
        type=float,
        nargs=2,
        default=[0.0, 0.0],
        metavar=("X", "Y"),
        help="アンカーポイント（デフォルト: 0 0 = 中央）",
    )
    parser.add_argument(
        "--vertical",
        action="store_true",
        default=False,
        help="縦動画用タイムライン（デフォルト: 横）",
    )
    parser.add_argument(
        "--auto-anchor",
        action="store_true",
        default=False,
        help="被写体位置からアンカーを自動検出（--vertical時のみ有効）",
    )
    parser.add_argument(
        "--no-auto-blur",
        action="store_true",
        default=False,
        help=(
            "動画内テキスト塗りつぶしオーバーレイ PNG の生成をスキップ. "
            "デフォルトでは clip 候補の time_ranges を OCR + track 化し、"
            "全 track の bbox を 1 枚の合成 PNG に OR 合成して FCPXML の V2 レーンに配置する."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="カスタムプロンプトファイルのパス",
    )
    parser.add_argument(
        "-n",
        "--no-cache",
        dest="use_cache",
        action="store_false",
        default=True,
        help="キャッシュを無視して再処理",
    )
    parser.add_argument(
        "--preset-dir",
        default=None,
        metavar="DIR",
        help="プリセット素材のディレクトリ（デフォルト: videos/と並列の preset/）",
    )
    parser.add_argument(
        "--no-frame",
        dest="no_frame",
        action="store_true",
        default=False,
        help="フレーム画像を適用しない",
    )
    parser.add_argument(
        "--no-bgm",
        dest="no_bgm",
        action="store_true",
        default=False,
        help="BGMを適用しない",
    )
    parser.add_argument(
        "--no-se",
        dest="no_se",
        action="store_true",
        default=False,
        help="効果音を適用しない",
    )
    parser.add_argument(
        "--no-title-image",
        dest="no_title_image",
        action="store_true",
        default=False,
        help="タイトル画像を生成しない",
    )
    parser.add_argument(
        "--title-target-size",
        type=str,
        default="1080x438",
        metavar="WxH",
        help="タイトル画像ターゲットサイズ（幅x高さ、例: 1080x438）",
    )
    parser.add_argument(
        "--title-offset-y",
        type=int,
        default=0,
        metavar="PX",
        help="タイトル表示位置の垂直オフセット（px、正=下方向、例: 50）",
    )
    parser.add_argument(
        "-s",
        "--simulate",
        action="store_true",
        default=False,
        help="ファイルを処理せず、対象ファイル一覧のみ表示",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="進捗出力を抑制する",
    )
    return parser


def run_suggest(argv: list[str]) -> None:
    """suggestサブコマンドを実行する"""
    parser = build_suggest_parser()
    args = parser.parse_args(argv)

    # ファイル収集（引数なし → ./videos/ をフォールバック）
    from textffcut_cli.command import _collect_video_paths

    file_args = args.files
    if not file_args:
        videos_dir = Path.cwd() / "videos"
        if videos_dir.exists():
            file_args = [str(videos_dir)]
            console.print(f"[dim]引数なし → {videos_dir}/ を自動検索[/]")
        else:
            console.print("[red]エラー: ファイルが指定されていません[/]")
            console.print("  使い方: textffcut clip [動画ファイル ...]")
            console.print("  または: textffcut setup で初期設定を行ってください")
            sys.exit(1)
    video_paths = _collect_video_paths(file_args)

    if args.simulate:
        _print_simulate(video_paths, args)
        return

    if not video_paths:
        console.print("[red]エラー: 対象ファイルが見つかりませんでした[/]")
        sys.exit(1)

    # APIキーチェック（暗号化ファイル → config.json → .env → 環境変数）
    from utils.api_key_manager import api_key_manager
    from textffcut_cli.setup_command import get_config_value

    api_key = api_key_manager.load_api_key()
    if not api_key:
        api_key = get_config_value("openai_api_key")
    if not api_key:
        console.print(
            "[red]エラー: OpenAI APIキーが設定されていません[/]\n"
            "  textffcut setup で設定するか、環境変数を設定してください:\n"
            "  [cyan]export OPENAI_API_KEY=sk-...[/]"
        )
        sys.exit(1)

    # 注: suggestコマンドではMLX環境チェックとライセンスチェックをスキップ
    # 文字起こしキャッシュがあればMLXなしでも動作する。
    # キャッシュがなく文字起こしが必要な場合は、transcribe時にエラーになる。

    # DIコンテナは文字起こしキャッシュがない場合にのみ必要
    # （suggestコマンドはOpenAI API呼び出しがメインで、streamlit不要）
    container = None

    # 各動画を処理
    total_cost = 0.0
    total_exported = 0

    for video_path in video_paths:
        cost, exported = _process_single_video(
            video_path=video_path,
            container=container,
            api_key=api_key,
            args=args,
        )
        total_cost += cost
        total_exported += exported

    # サマリー
    if len(video_paths) > 1:
        console.print()
        console.print(f"[bold]合計: {total_exported}件のFCPXML | " f"APIコスト: 約{total_cost * 150:.1f}円[/]")


def _process_single_video(
    video_path: Path,
    container,
    api_key: str,
    args: argparse.Namespace,
) -> tuple[float, int]:
    """1つの動画を処理し、(cost, exported_count) を返す"""
    console.print(f"\n[bold]📝 文字起こし...[/] {video_path.name}")

    # 文字起こし（キャッシュ優先）
    transcription = _transcribe(video_path, container, args)
    if transcription is None:
        return 0.0, 0

    # AI候補生成→FCPXML出力
    console.print(f"\n[bold]🤖 AI切り抜き候補を生成中...[/]")
    speed_info = f" | 速度: {args.speed}x" if args.speed != 1.0 else ""

    # gateway 構築 (build_gateway helper で GUI/CLI 統一、issue #153)
    quality_info = f" | 品質評価: {args.quality_model}" if args.quality_model != args.ai_model else ""
    console.print(f"  モデル: {args.ai_model}{quality_info} | 候補数: {args.num}{speed_info}")

    from infrastructure.external.gateways.openai_clip_suggestion_gateway import build_gateway
    from use_cases.ai.suggest_and_export import (
        SuggestAndExportRequest,
        SuggestAndExportUseCase,
    )

    gateway = build_gateway(
        api_key=api_key,
        ai_model=args.ai_model,
        quality_model=args.quality_model,
    )
    use_case = SuggestAndExportUseCase(gateway=gateway)

    # メディア素材検出サマリー
    from utils.media_asset_detector import detect_media_assets

    preset_dir = Path(args.preset_dir) if args.preset_dir else None
    media_preview = detect_media_assets(
        video_path.resolve(),
        preset_dir,
        enable_frame=not args.no_frame,
        enable_bgm=not args.no_bgm,
        enable_se=not args.no_se,
    )
    if media_preview.has_any:
        console.print(f"  🎨 {media_preview.summary()}")

    # タイトル画像ターゲットサイズのパース
    title_target_size = None
    if not args.no_title_image:
        try:
            tw, th = args.title_target_size.split("x")
            title_target_size = (int(tw), int(th))
        except (ValueError, AttributeError):
            console.print(
                f"[yellow]⚠ --title-target-size の形式が不正です: {args.title_target_size}。デフォルト(1080x438)を使用[/]"
            )
            title_target_size = (1080, 438)

    request = SuggestAndExportRequest(
        video_path=video_path.resolve(),
        transcription=transcription,
        ai_model=args.ai_model,
        quality_model=args.quality_model,
        num_candidates=args.num,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        prompt_path=args.prompt,
        remove_silence=args.remove_silence,
        generate_srt=args.generate_srt,
        srt_max_chars=args.srt_max_chars,
        srt_max_lines=args.srt_max_lines,
        preset_dir=preset_dir,
        enable_frame=not args.no_frame,
        enable_bgm=not args.no_bgm,
        enable_se=not args.no_se,
        speed=args.speed,
        scale=(args.zoom / 100.0, args.zoom / 100.0),
        anchor=tuple(args.anchor),
        timeline_resolution="vertical" if args.vertical else "horizontal",
        enable_title_image=not args.no_title_image,
        title_target_size=title_target_size,
        title_offset_y=args.title_offset_y,
        auto_anchor=args.auto_anchor,
        enable_blur_overlay=not args.no_auto_blur,
    )

    result = use_case.execute(request)

    cost_jpy = result.detection_cost_usd * 150
    console.print(
        f"  ✓ 話題{len(result.suggestions)}件検出" f"（{result.detection_processing_time:.1f}秒、約{cost_jpy:.1f}円）"
    )

    # 各候補の情報表示
    if not args.quiet and result.suggestions:
        console.print(f"\n[bold]🔧 機械的編集 → AI選定...[/]")
        for i, s in enumerate(result.suggestions, 1):
            console.print(f"  候補{i}: {s.title}（{s.total_duration:.0f}秒、{s.variant_label}）")

    # FCPXML出力結果
    if result.exported_files:
        console.print(f"\n[bold]🎬 生成完了[/]")
        for path in result.exported_files:
            console.print(f"  ✓ {path.name}")
            # 対応するSRTファイルがあれば表示
            srt_path = path.with_suffix(".srt")
            if srt_path.exists():
                console.print(f"  ✓ {srt_path.name} [dim](字幕)[/]")

        # タイトル画像の表示
        title_dir = result.output_dir.parent / "title_images"
        if title_dir.exists():
            title_count = len(list(title_dir.glob("*.png")))
            total_suggestions = len(result.suggestions)
            if title_count > 0:
                if title_count < total_suggestions and not args.no_title_image:
                    failed = total_suggestions - title_count
                    console.print(
                        f"  🖼 タイトル画像: {title_count}枚 [dim]({title_dir.name}/)[/]"
                        f" [yellow]({failed}件失敗、フォントが見つからない可能性)[/]"
                    )
                else:
                    console.print(f"  🖼 タイトル画像: {title_count}枚 [dim]({title_dir.name}/)[/]")

        console.print(f"\n📁 出力: {result.output_dir}/ （{len(result.exported_files)}件）")
    else:
        console.print("[yellow]⚠ FCPXML生成候補がありませんでした[/]")

    return result.detection_cost_usd, len(result.exported_files)


def _transcribe(video_path: Path, container, args) -> "TranscriptionResult | None":
    """文字起こしを実行する（キャッシュ優先）"""
    # まずキャッシュから読み込みを試みる
    cached = _load_transcription_cache(video_path, args.model)
    if cached is not None:
        console.print(f"  モデル: {args.model} | ✓ キャッシュから読み込み")
        return cached

    # キャッシュがなければDI経由で文字起こし実行
    try:
        from domain.value_objects import FilePath
        from use_cases.transcription.transcribe_video import TranscribeVideoRequest, TranscribeVideoUseCase

        gateway = container.gateways.transcription_gateway()
        use_case = TranscribeVideoUseCase(gateway)

        request = TranscribeVideoRequest(
            video_path=FilePath(str(video_path)),
            model_size=args.model,
            language=None,
            use_cache=args.use_cache,
        )

        result = use_case(request)
        return result.transcription
    except Exception as e:
        console.print(f"  [red]✗ 文字起こし失敗: {e}[/]")
        console.print(f"  [dim]ヒント: 先に textffcut {video_path.name} で文字起こしを実行してください[/]")
        return None


def _load_transcription_cache(video_path: Path, model: str) -> "TranscriptionResult | None":
    """文字起こしキャッシュから直接読み込む"""
    cache_dir = video_path.parent / f"{video_path.stem}_TextffCut" / "transcriptions"
    cache_file = cache_dir / f"{model}.json"

    if not cache_file.exists():
        # 別モデルのキャッシュがあるか確認
        if cache_dir.exists():
            available = [f.stem for f in cache_dir.glob("*.json")]
            if available:
                console.print(f"  [yellow]モデル '{model}' のキャッシュなし。" f"利用可能: {', '.join(available)}[/]")
                # 最初に見つかったキャッシュを使う
                cache_file = cache_dir / f"{available[0]}.json"
                console.print(f"  → {available[0]} のキャッシュを使用")
            else:
                return None
        else:
            return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))

        # word-level タイムスタンプが無いキャッシュは SRT 境界ズレを起こすため再文字起こしさせる
        segments = data.get("segments", [])
        if segments and not all(s.get("words") for s in segments):
            console.print(
                "  [yellow]キャッシュに word-level タイムスタンプが無いため、"
                "再文字起こしします（SRT字幕精度のため）[/]"
            )
            return None

        from domain.entities.transcription import TranscriptionResult

        return TranscriptionResult(
            id=f"cache_{video_path.stem}",
            video_id=str(video_path),
            language=data.get("language", "ja"),
            segments=segments,
            duration=segments[-1]["end"] if segments else 0.0,
            original_audio_path=data.get("original_audio_path", ""),
            model_size=data.get("model_size", model),
            processing_time=data.get("processing_time", 0.0),
        )
    except Exception as e:
        console.print(f"  [yellow]キャッシュ読み込みエラー: {e}[/]")
        return None


def _print_simulate(paths: list[Path], args: argparse.Namespace) -> None:
    console.print("\n[bold]シミュレート[/] — 実際の処理は行いません\n")
    console.print(f"文字起こしモデル: [cyan]{args.model}[/]")
    console.print(f"AIモデル: [cyan]{args.ai_model}[/]")
    console.print(f"候補数: {args.num} | {args.min_duration}-{args.max_duration}秒")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("ファイル")
    table.add_column("パス", style="dim")

    for i, p in enumerate(paths, 1):
        table.add_row(str(i), p.name, str(p.parent))

    console.print(table)
    if paths:
        console.print(f"\n合計: [bold]{len(paths)}[/] ファイル")
    else:
        console.print("\n[yellow]対象ファイルが見つかりませんでした[/]")
