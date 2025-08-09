#!/usr/bin/env python3
"""
実際の動画ファイルでのテスト
"""
import os
import sys
import time

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from core.transcription_optimized import OptimizedTranscriber


def test_real_video(video_path: str):
    """実際の動画でテスト"""
    print(f"\n{'=' * 60}")
    print("実際の動画でのテスト")
    print(f"動画ファイル: {video_path}")
    print(f"{'=' * 60}\n")

    # 動画情報を取得
    from core.video import VideoInfo

    try:
        video_info = VideoInfo.from_file(video_path)
        print(f"動画時間: {video_info.duration:.1f}秒 ({video_info.duration / 60:.1f}分)")
        print(f"解像度: {video_info.width}x{video_info.height}")
        print(f"FPS: {video_info.fps:.1f}")
        print(f"コーデック: {video_info.codec}")
    except Exception as e:
        print(f"動画情報の取得エラー: {e}")
        return

    # 設定
    config = Config()

    # APIキーの確認
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEYが設定されていません。ローカルモードのみテストします。")
        test_modes = ["local"]
    else:
        print("\n✅ APIキーが設定されています。両方のモードでテストします。")
        test_modes = ["local", "api"]

    results = {}

    # 各モードでテスト
    for mode in test_modes:
        print(f"\n[{mode.upper()}モード テスト]")

        if mode == "api":
            config.transcription.use_api = True
            config.transcription.api_key = api_key
            config.transcription.api_provider = "openai"
        else:
            config.transcription.use_api = False

        transcriber = OptimizedTranscriber(config)

        # プログレス表示
        def progress_callback(progress: float, status: str):
            print(f"  {progress * 100:.1f}% - {status}")

        # 文字起こし実行
        start_time = time.time()
        try:
            result = transcriber.transcribe(
                video_path,
                model_size="base" if mode == "local" else "whisper-1",
                progress_callback=progress_callback,
                use_cache=False,
                save_cache=True,
            )

            elapsed_time = time.time() - start_time

            # 結果を保存
            results[mode] = {
                "success": True,
                "time": elapsed_time,
                "segments": len(result.segments),
                "sample_text": result.segments[0].text if result.segments else "（文字起こし結果なし）",
            }

            print("\n  ✅ 成功")
            print(f"  処理時間: {elapsed_time:.1f}秒 (x{video_info.duration / elapsed_time:.1f}速)")
            print(f"  セグメント数: {len(result.segments)}")
            print(f"  最初のテキスト: {results[mode]['sample_text'][:50]}...")

            if mode == "api":
                # API料金の計算
                api_cost = (video_info.duration / 60) * 0.006
                print(f"  API料金: ${api_cost:.3f} (約{api_cost * 150:.0f}円)")

        except Exception as e:
            results[mode] = {"success": False, "error": str(e)}
            print(f"\n  ❌ エラー: {e}")

    # 結果サマリー
    print(f"\n{'=' * 60}")
    print("📊 結果サマリー")
    print(f"{'=' * 60}")

    if "local" in results and results["local"]["success"]:
        print(f"ローカルモード: {results['local']['time']:.1f}秒 ({results['local']['segments']}セグメント)")

    if "api" in results and results["api"]["success"]:
        print(f"APIモード: {results['api']['time']:.1f}秒 ({results['api']['segments']}セグメント)")

        if "local" in results and results["local"]["success"]:
            speedup = results["local"]["time"] / results["api"]["time"]
            print(f"APIによる高速化: x{speedup:.1f}")


def main():
    """メイン関数"""
    import argparse

    parser = argparse.ArgumentParser(description="実際の動画でのTextffCutテスト")
    parser.add_argument("video_path", help="テストする動画ファイルのパス")

    args = parser.parse_args()

    # ファイルの存在確認
    if not os.path.exists(args.video_path):
        print(f"エラー: 動画ファイルが見つかりません: {args.video_path}")
        sys.exit(1)

    test_real_video(args.video_path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        print("使用方法:")
        print("  python test_real_video.py <動画ファイルパス>")
        print("")
        print("例:")
        print("  python test_real_video.py /path/to/video.mp4")
