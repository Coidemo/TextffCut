# Text+ Prototype

DaVinci Resolve の Subtitle トラック (SRT 字幕) を Fusion Text+ クリップに変換するプロトタイプ。Snap Captions (有償 Lua スクリプト) と同等の挙動を Resolve Python Scripting API のみで再現する。実機検証用に作成し、その後 `infrastructure/davinci_resolve.py` に統合する想定。

## 事前準備

1. DaVinci Resolve を起動し、対象プロジェクトを開く
2. **Preferences > System > General > External scripting using: Local** を有効化
3. Media Pool の root に `TextffCut` ビンを作成
4. `TextffCut` ビン内に `Caption_Default` という Fusion Title (Text+) テンプレートを配置
   - 一番ラクな方法: Snap Captions Pack の「けんすう」テンプレを `TextffCut` ビンへドラッグ&ドロップでコピーし、`Caption_Default` にリネーム
5. SRT 字幕が乗った Subtitle トラック 1 を持つタイムラインを current にしておく

## 使い方

```bash
# 字幕を列挙するだけ (Resolve は変えない)
python convert_subtitles_to_text_plus.py --dry-run

# 既定で実行 (新規ビデオトラックを最上位に追加して配置)
python convert_subtitles_to_text_plus.py

# テンプレ・配置先トラックを指定
python convert_subtitles_to_text_plus.py --template Caption_Bold --video-track 5

# 各機能を OFF にしたい場合
python convert_subtitles_to_text_plus.py --no-fill-gaps --no-extend-edges --keep-subtitle
```

## 実装済み機能

| 機能 | デフォルト | 説明 |
|---|---|---|
| 新規ビデオトラック自動追加 | ON | `--video-track` 未指定時、最上位に新規 video track を追加して配置 |
| クリップ Green 着色 | 固定 | Snap Captions と同じ視認性 |
| Subtitle track 1 固定 | 固定 | 複数 subtitle track があっても track 1 のみ参照 (`--subtitle-track` で override 可) |
| Subtitle track 無効化 | ON | 処理成功時に subtitle track を無効化 (`--keep-subtitle` で維持) |
| U+2028 → \n 改行変換 | 固定 | Resolve が SRT 改行を U+2028 で保持しているため Text+ 用に変換 |
| Fill Gaps | ON | 次字幕までの gap が `--max-fill-frames` (10f) 以下なら end を伸ばす |
| duration_multiplier 補正 | ON | Fusion comp の内部 duration により実配置長が縮む現象を打ち消す (Snap Captions と同じ手法) |
| 端伸ばし (Extend Edges) | ON | 最初の字幕をタイムライン先頭、最後の字幕を末尾まで伸ばす |

## 実機検証で確認した API 挙動

実装中に判明した、ドキュメントだけでは見えない Resolve API の挙動:

- `subtitle_clip.GetName()` → 字幕テキストを返す (改行は U+2028)
- `subtitle_clip.GetStart()` / `GetEnd()` → タイムライン絶対フレーム
- `media_pool.AppendToTimeline()` の戻り値は配置成功でも `[None]` を返すことがある (要素ごと `GetName() is None` 判定が必要)
- `text_plus_tool.SetInput("StyledText", text)` の戻り値は信用できない (False を返すが副作用は効いている)
- `timeline.GetEndFrame()` は exclusive (= 末端フレーム + 1)
- Fusion Title をメディアプールに置いても、`AppendToTimeline` で指定した `endFrame` と実際の配置長は一致しない (内部固有 duration による)

## 既知の制約

- `.drb` ファイルの自動インポートは Python API でサポートされていないため、ユーザーが事前に `TextffCut` ビンを作成しテンプレートを入れておく前提
- 1 ファイルの subtitle track のみ対象 (複数 subtitle track の混在は track 1 を採用)
- TextffCut の SRT は字幕間 gap=0 (連続字幕) で出力されるため、Fill Gaps は実質 no-op になる。ユーザーが Resolve 上で字幕を編集して gap を作った場合の保険として残してある

## TextffCut 統合への移行

このプロトタイプの動作確認後、以下の作業で TextffCut に組み込む:

1. ロジックを `infrastructure/davinci_resolve.py::convert_subtitles_to_text_plus()` として移植
2. `send_clip_to_resolve()` に `text_plus: bool = False` パラメータ追加
3. `textffcut_cli/send_command.py` に `--text-plus` フラグ追加 → SRT import 後に自動変換
4. CLAUDE.md にユーザー向けセットアップ手順を追記

## ライセンスについて

Snap Captions のコード (`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/Snap Captions.lua`) は再配布禁止 (使用は自由) のため、コードは一切コピーしていない。Subtitle トラックから字幕を取り出し、テンプレートを複製して Text+ ノードのテキストを差し替える処理パターンと duration_multiplier 補正の考え方は Resolve API の標準的な使い方であり、独自実装。
