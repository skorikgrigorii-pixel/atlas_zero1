import pytest

from az_enterprise.core.story_strategy_contract_rc2 import (
    NarrativeTransitionRC2,
    StoryActRC2,
    StorySceneRC2,
    StoryStrategyRC2,
    StoryStrategyResultRC2,
)


def build_result():
    strategy = StoryStrategyRC2(
        film_type="documentary",
        narrative_strategy="event_progression",
        language="ru",
        target_duration_sec=1500.0,
        target_audience="18-55",
        use_existing_assets_only=True,
        allow_generated_visuals=False,
    )

    act = StoryActRC2(
        act_id="ACT01",
        title_ru="???????? ??????????",
        narrative_goal_ru=(
            "??????????? ??????? ? ??????????."
        ),
        order=1,
        duration_sec=1500.0,
    )

    scene_1 = StorySceneRC2(
        scene_id="SC01",
        act_id="ACT01",
        title_ru="????? ? ?????????",
        narrative_goal_ru=(
            "???????? ???????? ????? ??????????."
        ),
        emotional_goal_ru="????????",
        visual_strategy_ru=(
            "????? ????? ?????? ? ??????????."
        ),
        order=1,
        duration_sec=750.0,
        cluster_ids=("cluster-monument-day",),
        asset_ids=("asset-1",),
    )

    scene_2 = StorySceneRC2(
        scene_id="SC02",
        act_id="ACT01",
        title_ru="?????? ?????",
        narrative_goal_ru=(
            "????????? ??????? ????? ? ??????."
        ),
        emotional_goal_ru="???????????",
        visual_strategy_ru=(
            "????????? ? ???????? ?????."
        ),
        order=2,
        duration_sec=750.0,
        cluster_ids=(
            "cluster-fireworks-night",
            "cluster-crema-night",
        ),
        asset_ids=("asset-2",),
    )

    transition = NarrativeTransitionRC2(
        from_scene_id="SC01",
        to_scene_id="SC02",
        transition_type="narrator_bridge",
        rationale_ru=(
            "??????? ?? ???????? ????????? "
            "? ?????? ???????????."
        ),
        narrator_bridge_required=True,
    )

    return StoryStrategyResultRC2(
        project_id="hogueras",
        strategy=strategy,
        acts=(act,),
        scenes=(scene_1, scene_2),
        transitions=(transition,),
    )


def test_contract_serializes():
    result = build_result().to_dict()

    assert result["project_id"] == "hogueras"
    assert len(result["acts"]) == 1
    assert len(result["scenes"]) == 2
    assert len(result["transitions"]) == 1


def test_existing_assets_only_blocks_generation():
    strategy = StoryStrategyRC2(
        film_type="documentary",
        narrative_strategy="event_progression",
        language="ru",
        target_duration_sec=1500.0,
        target_audience="18-55",
        use_existing_assets_only=True,
        allow_generated_visuals=True,
    )

    with pytest.raises(
        ValueError,
        match="cannot allow",
    ):
        strategy.validate()


def test_scene_requires_known_act():
    result = build_result()

    invalid_scene = StorySceneRC2(
        scene_id="SC01",
        act_id="UNKNOWN",
        title_ru="??????",
        narrative_goal_ru="????????",
        emotional_goal_ru="neutral",
        visual_strategy_ru="test",
        order=1,
        duration_sec=1500.0,
        cluster_ids=("cluster-1",),
        asset_ids=("asset-1",),
    )

    invalid = StoryStrategyResultRC2(
        project_id="hogueras",
        strategy=result.strategy,
        acts=result.acts,
        scenes=(invalid_scene,),
        transitions=(),
    )

    with pytest.raises(
        ValueError,
        match="unknown act",
    ):
        invalid.validate()


def test_transitions_must_follow_scene_order():
    result = build_result()

    invalid_transition = NarrativeTransitionRC2(
        from_scene_id="SC02",
        to_scene_id="SC01",
        transition_type="cut",
        rationale_ru="???????? ???????.",
        narrator_bridge_required=False,
    )

    invalid = StoryStrategyResultRC2(
        project_id=result.project_id,
        strategy=result.strategy,
        acts=result.acts,
        scenes=result.scenes,
        transitions=(invalid_transition,),
    )

    with pytest.raises(
        ValueError,
        match="follow scene order",
    ):
        invalid.validate()


def test_scene_duration_matches_target():
    result = build_result()

    invalid_strategy = StoryStrategyRC2(
        film_type="documentary",
        narrative_strategy="event_progression",
        language="ru",
        target_duration_sec=1600.0,
        target_audience="18-55",
        use_existing_assets_only=True,
        allow_generated_visuals=False,
    )

    invalid = StoryStrategyResultRC2(
        project_id=result.project_id,
        strategy=invalid_strategy,
        acts=result.acts,
        scenes=result.scenes,
        transitions=result.transitions,
    )

    with pytest.raises(
        ValueError,
        match="target duration",
    ):
        invalid.validate()
