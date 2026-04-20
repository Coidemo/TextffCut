"""core/fcpxml_relink.py のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from core.fcpxml_relink import (
    RelinkStatus,
    _path_to_uri,
    _uri_to_path,
    relink_all_in_videos_root,
    relink_folder,
)

# ---------------------------------------------------------------------------
# URI ⇔ Path 変換
# ---------------------------------------------------------------------------


class TestUriPathConversion:
    def test_uri_to_path_basic(self):
        uri = "file:///Users/foo/bar.mp4"
        assert _uri_to_path(uri) == Path("/Users/foo/bar.mp4")

    def test_uri_to_path_url_encoded(self):
        uri = "file:///Users/foo/%E5%8B%95%E7%94%BB.mp4"
        assert _uri_to_path(uri) == Path("/Users/foo/動画.mp4")

    def test_path_to_uri_encodes_japanese(self):
        uri = _path_to_uri(Path("/Users/foo/動画.mp4"))
        assert uri == "file:///Users/foo/%E5%8B%95%E7%94%BB.mp4"

    def test_roundtrip(self):
        p = Path("/Users/naoki/videos/テスト動画.mp4")
        assert _uri_to_path(_path_to_uri(p)) == p


# ---------------------------------------------------------------------------
# フィクスチャ生成ヘルパ
# ---------------------------------------------------------------------------


def _make_fcpxml(
    video_uri: str,
    cache_uri: str | None = None,
    preset_uri: str | None = None,
) -> str:
    """テスト用FCPXMLを生成。"""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE fcpxml>",
        '<fcpxml version="1.9">',
        "    <resources>",
        '        <asset id="r1" name="v.mp4">',
        f'            <media-rep kind="original-media" src="{video_uri}"/>',
        "        </asset>",
    ]
    if cache_uri:
        parts += [
            '        <asset id="r2" name="title.png">',
            f'            <media-rep kind="original-media" src="{cache_uri}"/>',
            "        </asset>",
        ]
    if preset_uri:
        parts += [
            '        <asset id="r3" name="frame.png">',
            f'            <media-rep kind="original-media" src="{preset_uri}"/>',
            "        </asset>",
        ]
    parts += ["    </resources>", "</fcpxml>"]
    return "\n".join(parts)


def _setup_cache_dir(tmp_path: Path, video_name: str = "demo") -> tuple[Path, Path, Path]:
    """tmp_path 配下に videos/ + preset/ + cache_dir を構築。

    Returns:
        (cache_dir, videos_root, preset_root)
    """
    videos_root = tmp_path / "videos"
    videos_root.mkdir()
    preset_root = tmp_path / "preset"
    preset_root.mkdir()
    cache_dir = videos_root / f"{video_name}_TextffCut"
    cache_dir.mkdir()
    (cache_dir / "fcpxml").mkdir()
    return cache_dir, videos_root, preset_root


# ---------------------------------------------------------------------------
# relink_folder: 基本動作
# ---------------------------------------------------------------------------


class TestRelinkFolder:
    def test_error_when_not_textffcut_folder(self, tmp_path):
        normal_dir = tmp_path / "normal"
        normal_dir.mkdir()
        result = relink_folder(normal_dir)
        assert result.status == RelinkStatus.ERROR
        assert "TextffCut" in (result.error_message or "")

    def test_error_when_not_exists(self, tmp_path):
        result = relink_folder(tmp_path / "nowhere_TextffCut")
        assert result.status == RelinkStatus.ERROR

    def test_empty_folder_is_up_to_date(self, tmp_path):
        cache_dir, _, _ = _setup_cache_dir(tmp_path)
        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.UP_TO_DATE
        assert result.fcpxml_count == 0

    def test_already_correct_paths_up_to_date(self, tmp_path):
        """現在のパスと一致していれば書き換え不要。"""
        cache_dir, videos_root, preset_root = _setup_cache_dir(tmp_path)
        # 実ファイルを配置
        (videos_root / "demo.mp4").write_bytes(b"")
        (preset_root / "frame.png").write_bytes(b"")
        (cache_dir / "title.png").write_bytes(b"")

        video_uri = _path_to_uri(videos_root / "demo.mp4")
        cache_uri = _path_to_uri(cache_dir / "title.png")
        preset_uri = _path_to_uri(preset_root / "frame.png")
        (cache_dir / "fcpxml" / "a.fcpxml").write_text(_make_fcpxml(video_uri, cache_uri, preset_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.UP_TO_DATE
        assert result.fcpxml_count == 1
        assert result.rewritten_count == 0

    def test_rewrites_video_path_from_old_machine(self, tmp_path):
        """旧マシンの videos パスを現在の videos_root に書き換え。"""
        cache_dir, videos_root, preset_root = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")

        old_video_uri = "file:///old/machine/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_video_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED
        assert result.rewritten_count == 1

        new_text = fcpxml_path.read_text(encoding="utf-8")
        expected_uri = _path_to_uri(videos_root / "demo.mp4")
        assert expected_uri in new_text
        assert "/old/machine/videos/" not in new_text

    def test_rewrites_cache_internal_paths(self, tmp_path):
        """キャッシュ内部のアセット（title_images/, source_*.mp4）を書き換え。"""
        cache_dir, videos_root, preset_root = _setup_cache_dir(tmp_path)
        (cache_dir / "title_images").mkdir()
        (cache_dir / "title_images" / "01.png").write_bytes(b"")

        # 旧マシンの別videos/配下のキャッシュ → 現在のキャッシュに追従すべき
        old_cache_uri = "file:///old/machine/videos/demo_TextffCut/title_images/01.png"
        old_video_uri = "file:///old/machine/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_video_uri, cache_uri=old_cache_uri), encoding="utf-8")

        (videos_root / "demo.mp4").write_bytes(b"")
        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED

        new_text = fcpxml_path.read_text(encoding="utf-8")
        expected_cache_uri = _path_to_uri(cache_dir / "title_images" / "01.png")
        assert expected_cache_uri in new_text

    def test_rewrites_preset_paths(self, tmp_path):
        """preset/ 配下のアセットを現在の preset_root に書き換え。"""
        cache_dir, videos_root, preset_root = _setup_cache_dir(tmp_path)
        (preset_root / "frame.png").write_bytes(b"")
        (videos_root / "demo.mp4").write_bytes(b"")

        old_preset_uri = "file:///old/machine/preset/frame.png"
        old_video_uri = "file:///old/machine/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(
            _make_fcpxml(old_video_uri, preset_uri=old_preset_uri),
            encoding="utf-8",
        )

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED

        new_text = fcpxml_path.read_text(encoding="utf-8")
        expected_preset_uri = _path_to_uri(preset_root / "frame.png")
        assert expected_preset_uri in new_text

    def test_reports_missing_files(self, tmp_path):
        """書き換え先のファイルが存在しなければ missing_files に記録。"""
        cache_dir, videos_root, preset_root = _setup_cache_dir(tmp_path)
        # 動画もpresetも配置しない（=missing）
        old_video_uri = "file:///old/machine/videos/demo.mp4"
        old_preset_uri = "file:///old/machine/preset/frame.png"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(
            _make_fcpxml(old_video_uri, preset_uri=old_preset_uri),
            encoding="utf-8",
        )

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.MISSING_FILES
        assert len(result.missing_files) == 2
        assert result.rewritten_count == 1

    def test_preserves_unmapped_uris(self, tmp_path):
        """分類できないURIはそのまま残す。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")

        # 拡張子もvideos/もpreset/も含まない奇妙なURI
        weird_uri = "file:///some/other/unknown.xyz"
        video_uri = _path_to_uri(videos_root / "demo.mp4")
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(video_uri, cache_uri=weird_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert weird_uri in fcpxml_path.read_text(encoding="utf-8")
        assert weird_uri in result.unmapped_uris

    def test_processes_multiple_fcpxml(self, tmp_path):
        """複数FCPXMLを一括処理。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")
        old_uri = "file:///old/videos/demo.mp4"
        for i in range(3):
            (cache_dir / "fcpxml" / f"{i}.fcpxml").write_text(_make_fcpxml(old_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.fcpxml_count == 3
        assert result.rewritten_count == 3

    def test_idempotent(self, tmp_path):
        """2回目は no-op。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")
        old_uri = "file:///old/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_uri), encoding="utf-8")

        r1 = relink_folder(cache_dir)
        assert r1.rewritten_count == 1
        r2 = relink_folder(cache_dir)
        assert r2.rewritten_count == 0
        assert r2.status == RelinkStatus.UP_TO_DATE

    def test_file_localhost_uri_format(self, tmp_path):
        """file://localhost/... 形式のURIも正しく解釈して書き換え。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")

        old_uri = "file://localhost/old/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED

        new_text = fcpxml_path.read_text(encoding="utf-8")
        expected = _path_to_uri(videos_root / "demo.mp4")
        assert expected in new_text

    def test_uppercase_extension(self, tmp_path):
        """大文字拡張子（.MP4 等）もvideos本体として分類される。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.MP4").write_bytes(b"")

        old_uri = "file:///old/videos/demo.MP4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED

    def test_atomic_write_no_leftover_tmp(self, tmp_path):
        """書き換え後に .tmp ファイルが残らない。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path)
        (videos_root / "demo.mp4").write_bytes(b"")
        old_uri = "file:///old/videos/demo.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_uri), encoding="utf-8")

        relink_folder(cache_dir)

        tmp_files = list(cache_dir.rglob("*.tmp"))
        assert tmp_files == []

    def test_url_encoded_japanese_filename(self, tmp_path):
        """URLエンコードされた日本語ファイル名の旧URIを正しく書き換え。"""
        cache_dir, videos_root, _ = _setup_cache_dir(tmp_path, video_name="動画")
        (videos_root / "動画.mp4").write_bytes(b"")

        # 旧マシンのURL-encoded URI
        old_uri = "file:///old/videos/%E5%8B%95%E7%94%BB.mp4"
        fcpxml_path = cache_dir / "fcpxml" / "a.fcpxml"
        fcpxml_path.write_text(_make_fcpxml(old_uri), encoding="utf-8")

        result = relink_folder(cache_dir)
        assert result.status == RelinkStatus.RELINKED

        new_text = fcpxml_path.read_text(encoding="utf-8")
        expected = _path_to_uri(videos_root / "動画.mp4")
        assert expected in new_text


# ---------------------------------------------------------------------------
# relink_all_in_videos_root
# ---------------------------------------------------------------------------


class TestRelinkAll:
    def test_scans_all_textffcut_folders(self, tmp_path):
        videos_root = tmp_path / "videos"
        videos_root.mkdir()
        (tmp_path / "preset").mkdir()
        # 3つのキャッシュフォルダ + 無関係なフォルダ
        for name in ["a_TextffCut", "b_TextffCut", "c_TextffCut"]:
            d = videos_root / name
            d.mkdir()
        (videos_root / "notes").mkdir()  # 無関係

        results = relink_all_in_videos_root(videos_root)
        assert len(results) == 3
        assert {r.cache_dir.name for r in results} == {
            "a_TextffCut",
            "b_TextffCut",
            "c_TextffCut",
        }

    def test_missing_videos_root_returns_empty(self, tmp_path):
        results = relink_all_in_videos_root(tmp_path / "nowhere")
        assert results == []
