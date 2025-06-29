#!/usr/bin/env python3
"""
SRT字幕の自然な改行処理のテスト
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.srt_diff_exporter import SRTDiffExporter
from core.text_processor import TextDifference, TextPosition
from core.transcription import TranscriptionResult, TranscriptionSegment
from utils.logging import get_logger

logger = get_logger(__name__)


def create_test_transcription() -> TranscriptionResult:
    """テスト用の文字起こし結果を作成"""
    # TranscriptionSegmentオブジェクトを作成
    segments = [
        TranscriptionSegment(
            start=0.0,
            end=5.0,
            text="これは長いテキストのサンプルです。日本語の自然な改行処理をテストしています。",
            words=[
                {"word": "これは", "start": 0.0, "end": 0.5},
                {"word": "長い", "start": 0.5, "end": 1.0},
                {"word": "テキストの", "start": 1.0, "end": 1.5},
                {"word": "サンプルです", "start": 1.5, "end": 2.0},
                {"word": "。", "start": 2.0, "end": 2.1},
                {"word": "日本語の", "start": 2.5, "end": 3.0},
                {"word": "自然な", "start": 3.0, "end": 3.5},
                {"word": "改行処理を", "start": 3.5, "end": 4.0},
                {"word": "テストしています", "start": 4.0, "end": 4.5},
                {"word": "。", "start": 4.5, "end": 4.6},
            ],
        ),
        TranscriptionSegment(
            start=5.0,
            end=10.0,
            text="6月5日の木曜日かな木曜日は18時でございます。長い文章を適切に分割できるかテストします。",
            words=[
                {"word": "6月5日の", "start": 5.0, "end": 5.8},
                {"word": "木曜日かな", "start": 5.8, "end": 6.5},
                {"word": "木曜日は", "start": 6.5, "end": 7.0},
                {"word": "18時で", "start": 7.0, "end": 7.5},
                {"word": "ございます", "start": 7.5, "end": 8.0},
                {"word": "。", "start": 8.0, "end": 8.1},
                {"word": "長い", "start": 8.2, "end": 8.5},
                {"word": "文章を", "start": 8.5, "end": 9.0},
                {"word": "適切に", "start": 9.0, "end": 9.3},
                {"word": "分割できるか", "start": 9.3, "end": 9.6},
                {"word": "テストします", "start": 9.6, "end": 9.9},
                {"word": "。", "start": 9.9, "end": 10.0},
            ],
        ),
    ]

    return TranscriptionResult(
        segments=segments, language="ja", original_audio_path="test.wav", model_size="base", processing_time=1.0
    )


def test_natural_line_breaks() -> None:
    """自然な改行処理のテスト"""
    config = Config()
    exporter = SRTDiffExporter(config)

    # テスト設定（11文字×2行）
    srt_settings = {
        "max_line_length": 11,
        "max_lines": 2,
        "min_duration": 0.5,
        "max_duration": 7.0,
        "gap_threshold": 0.1,
        "fps": 30.0,
    }

    # テスト用の差分検出結果
    transcription = create_test_transcription()

    # 共通部分を追加（切り抜き対象）
    common_positions = [
        TextPosition(
            start=0,
            end=40,
            text="これは長いテキストのサンプルです。日本語の自然な改行処理をテストしています。",
        ),
        TextPosition(
            start=41,
            end=85,
            text="6月5日の木曜日かな木曜日は18時でございます。長い文章を適切に分割できるかテストします。",
        ),
    ]

    # 元のテキストを構築
    original_text = "これは長いテキストのサンプルです。日本語の自然な改行処理をテストしています。6月5日の木曜日かな木曜日は18時でございます。長い文章を適切に分割できるかテストします。"

    diff = TextDifference(
        original_text=original_text,
        edited_text=original_text,  # 編集なし
        common_positions=common_positions,
        added_chars=set(),
    )

    # SRTエクスポート
    output_path = "test_output_natural.srt"
    success = exporter.export_from_diff(
        diff=diff,
        transcription_result=transcription,
        output_path=output_path,
        srt_settings=srt_settings,
    )

    if success:
        logger.info(f"SRTファイルが生成されました: {output_path}")

        # 生成されたファイルを読み込んで表示
        with open(output_path, encoding="utf-8") as f:
            content = f.read()
            print("\n=== 生成されたSRT ===")
            print(content)

        # 各字幕エントリの行文字数をチェック
        entries = content.strip().split("\n\n")
        for entry in entries:
            lines = entry.split("\n")
            if len(lines) >= 3:  # インデックス、時間、テキスト
                text_lines = lines[2:]  # テキスト部分
                print(f"\n字幕 {lines[0]}:")
                for i, line in enumerate(text_lines):
                    print(f"  {i + 1}行目: 「{line}」 ({len(line)}文字)")
                    if len(line) > 11:
                        print(f"  ⚠️ 警告: {i + 1}行目が11文字を超えています！")
    else:
        logger.error("SRTファイルの生成に失敗しました")

    # テストファイルを削除
    Path(output_path).unlink(missing_ok=True)


def test_long_text_splitting() -> None:
    """長いテキストの分割テスト"""
    from core.japanese_line_break import JapaneseLineBreakRules

    # テストケース
    test_cases = [
        "これは非常に長い日本語のテキストで、複数のチャンクに分割される必要があります。禁則処理も正しく適用されるかテストします。",
        "（括弧で始まる文章）や、句読点が連続する場合、、、適切に処理されるか確認します。",
        "数字を含む文章123や、英単語mixedのテキストも自然に改行されるはずです。",
        "2025年1月15日の予定は、10時30分から会議があります。",
    ]

    max_line_length = 15

    for i, text in enumerate(test_cases):
        print(f"\n=== テストケース {i + 1} ===")
        print(f"元のテキスト: 「{text}」")
        print(f"文字数: {len(text)}")

        # 1行ずつ抽出
        remaining = text
        line_num = 1
        while remaining:
            line, remaining = JapaneseLineBreakRules.extract_line(remaining, max_line_length)
            print(f"{line_num}行目: 「{line}」 ({len(line)}文字)")
            line_num += 1


if __name__ == "__main__":
    print("=== SRT自然な改行処理テスト ===\n")

    # 基本的な改行処理のテスト
    test_natural_line_breaks()

    print("\n" + "=" * 50 + "\n")

    # 長いテキストの分割テスト
    test_long_text_splitting()
