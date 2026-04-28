"""build_gateway helper の単体テスト (issue #153)。

GUI/CLI で重複していた gateway 構築 + model_overrides 組み立て処理を
`infrastructure/external/gateways/openai_clip_suggestion_gateway.py::build_gateway`
に集約した。本テストは override の有無/中身が想定通りか検証する。
"""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.external.gateways.openai_clip_suggestion_gateway import (
    QUALITY_OVERRIDE_METHODS,
    build_gateway,
)


def _build(ai_model: str, quality_model: str | None):
    """OpenAI クライアント生成を mock してから build_gateway を呼ぶ。"""
    with patch(
        "infrastructure.external.gateways.openai_clip_suggestion_gateway.OpenAI"
    ):
        return build_gateway(api_key="dummy", ai_model=ai_model, quality_model=quality_model)


def test_quality_model_None_means_no_override():
    """quality_model=None なら override は空。"""
    gw = _build(ai_model="gpt-4.1-mini", quality_model=None)
    assert gw._model_overrides == {}
    assert gw.model == "gpt-4.1-mini"


def test_quality_model_equals_ai_model_means_no_override():
    """quality_model == ai_model なら override は空 (冗長指定の安全動作)。"""
    gw = _build(ai_model="gpt-4.1-mini", quality_model="gpt-4.1-mini")
    assert gw._model_overrides == {}


def test_quality_model_differs_applies_override_to_listed_methods_only():
    """quality_model != ai_model なら QUALITY_OVERRIDE_METHODS 全件に override。

    一覧外メソッド (タイトル画像 / SE 配置) には override されない。
    """
    gw = _build(ai_model="gpt-4.1-mini", quality_model="gpt-4.1")
    assert set(gw._model_overrides.keys()) == set(QUALITY_OVERRIDE_METHODS)
    assert all(v == "gpt-4.1" for v in gw._model_overrides.values())
    # ベースモデルは ai_model のまま
    assert gw.model == "gpt-4.1-mini"


def test_quality_method_list_is_complete():
    """QUALITY_OVERRIDE_METHODS が AI 経路で実際に呼ばれている主要 method を網羅。

    drift 防止のための regression test。新しい sub-step を追加したらこの
    リストを更新する必要があることを明示する。
    """
    expected = {
        "detect_topics",
        "evaluate_clip_quality",
        "trim_clips",
        "select_best_clip",
        "judge_segment_relevance",
        "refine_topic_boundary",
        "find_core_and_conclusion",
    }
    assert set(QUALITY_OVERRIDE_METHODS) == expected


def test_resolve_model_falls_back_to_base_when_no_override():
    """_resolve_model: override 無しの method は ai_model を返す (タイトル画像等)。"""
    gw = _build(ai_model="gpt-4.1-mini", quality_model="gpt-4.1")
    # 一覧外
    assert gw._resolve_model("title_image_design") == "gpt-4.1-mini"
    # 一覧内
    assert gw._resolve_model("detect_topics") == "gpt-4.1"
