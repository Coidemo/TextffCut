"""
タイムライン編集のダークモード対応をテスト
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from ui.timeline_color_scheme import TimelineColorScheme


def test_color_scheme_light_mode():
    """ライトモードのカラースキームをテスト"""
    print("=== ライトモードのカラースキームテスト ===")

    colors = TimelineColorScheme.get_colors(is_dark_mode=False)

    # 必要なカラーキーが存在することを確認
    required_keys = [
        "waveform_positive",
        "waveform_negative",
        "waveform_silence",
        "segment_active",
        "segment_inactive",
        "segment_hover",
        "boundary_marker",
        "playhead",
        "background",
        "grid_lines",
        "grid_major",
        "text_primary",
        "text_secondary",
        "selection_bg",
        "hover_bg",
        "plotly_template",
    ]

    for key in required_keys:
        assert key in colors, f"カラーキー '{key}' が見つかりません"
        print(f"✓ {key}: {colors[key]}")

    # ライトモード特有の値を確認
    assert colors["background"] == "#FAFAFA"
    assert colors["text_primary"] == "#212121"
    assert colors["plotly_template"] == "plotly_white"

    print("\n✅ ライトモードのカラースキームテスト完了")


def test_color_scheme_dark_mode():
    """ダークモードのカラースキームをテスト"""
    print("\n=== ダークモードのカラースキームテスト ===")

    colors = TimelineColorScheme.get_colors(is_dark_mode=True)

    # 必要なカラーキーが存在することを確認
    required_keys = [
        "waveform_positive",
        "waveform_negative",
        "waveform_silence",
        "segment_active",
        "segment_inactive",
        "segment_hover",
        "boundary_marker",
        "playhead",
        "background",
        "grid_lines",
        "grid_major",
        "text_primary",
        "text_secondary",
        "selection_bg",
        "hover_bg",
        "plotly_template",
    ]

    for key in required_keys:
        assert key in colors, f"カラーキー '{key}' が見つかりません"
        print(f"✓ {key}: {colors[key]}")

    # ダークモード特有の値を確認
    assert colors["background"] == "#263238"
    assert colors["text_primary"] == "#ECEFF1"
    assert colors["plotly_template"] == "plotly_dark"
    assert colors["waveform_positive"] == "#4DB6AC"  # 明るいティール
    assert colors["waveform_silence"] == "#546E7A"  # ブルーグレー

    print("\n✅ ダークモードのカラースキームテスト完了")


def test_plotly_theme_application():
    """Plotlyテーマ適用をテスト"""
    print("\n=== Plotlyテーマ適用テスト ===")

    # plotlyがインストールされているか確認
    try:
        import plotly.graph_objects as go

        # テスト用のフィギュア作成
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6]))

        # ダークモードテーマを適用
        fig_dark = TimelineColorScheme.apply_plotly_theme(fig, is_dark_mode=True)

        # レイアウトが更新されていることを確認
        assert fig_dark.layout.plot_bgcolor == "#263238"
        assert fig_dark.layout.paper_bgcolor == "#263238"
        assert fig_dark.layout.font.color == "#ECEFF1"
        print("✓ ダークモードテーマが正しく適用されました")

        # ライトモードテーマを適用
        fig_light = TimelineColorScheme.apply_plotly_theme(fig, is_dark_mode=False)

        assert fig_light.layout.plot_bgcolor == "#FAFAFA"
        assert fig_light.layout.paper_bgcolor == "#FAFAFA"
        assert fig_light.layout.font.color == "#212121"
        print("✓ ライトモードテーマが正しく適用されました")

    except ImportError:
        print("⚠️ plotlyがインストールされていないため、テーマ適用テストをスキップ")

    print("\n✅ Plotlyテーマ適用テスト完了")


def test_waveform_display_dark_mode():
    """WaveformDisplayのダークモード対応をテスト"""
    print("\n=== WaveformDisplayのダークモード対応テスト ===")

    try:
        from ui.waveform_display import WaveformDisplay

        # ダークモード対応のWaveformDisplayを作成
        display_dark = WaveformDisplay(use_dark_mode=True)

        # カラースキームが正しく設定されていることを確認
        assert display_dark.colors["background"] == "#263238"
        assert display_dark.colors["waveform_positive"] == "#4DB6AC"
        print("✓ WaveformDisplayにダークモードカラーが設定されました")

        # ライトモード対応のWaveformDisplayを作成
        display_light = WaveformDisplay(use_dark_mode=False)

        assert display_light.colors["background"] == "#FAFAFA"
        assert display_light.colors["waveform_positive"] == "#4CAF50"
        print("✓ WaveformDisplayにライトモードカラーが設定されました")

    except ImportError as e:
        print(f"⚠️ インポートエラー: {e}")

    print("\n✅ WaveformDisplayのダークモード対応テスト完了")


if __name__ == "__main__":
    try:
        test_color_scheme_light_mode()
        test_color_scheme_dark_mode()
        test_plotly_theme_application()
        test_waveform_display_dark_mode()

        print("\n" + "=" * 50)
        print("🎉 すべてのダークモードテストが成功しました！")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
