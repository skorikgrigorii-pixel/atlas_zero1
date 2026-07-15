import pytest

from az_enterprise.core.visual_understanding_contract_rc2 import (
    AssetUnderstandingRC2,
    ChronologyEntryRC2,
    EventClusterRC2,
    MissingEpisodeRC2,
    OffTopicAssetRC2,
    VisualUnderstandingResultRC2,
)


def make_asset(
    asset_id="asset-1",
    relevance_status="RELEVANT",
    off_topic_score=0.02,
):
    return AssetUnderstandingRC2(
        asset_id=asset_id,
        filename=f"{asset_id}.mp4",
        media_type="video",
        event_type="parade",
        event_confidence=0.92,
        relevance_status=relevance_status,
        relevance_score=0.95,
        off_topic_score=off_topic_score,
        time_period="day",
        description="Festival parade in Alicante",
        story_value=0.88,
        detected_objects=("crowd", "musicians"),
        detected_actions=("walking", "playing music"),
    )


def make_result():
    cluster = EventClusterRC2(
        cluster_id="cluster-parade",
        event_type="parade",
        title_ru="??????????? ???????",
        description_ru="????????? ???????? ?? ??????.",
        asset_ids=("asset-1",),
        confidence=0.92,
        time_period="day",
        chronology_order=1,
        total_duration_sec=42.0,
        story_value=0.88,
    )

    chronology = ChronologyEntryRC2(
        order=1,
        cluster_id="cluster-parade",
        event_type="parade",
        title_ru="???????",
        time_period="day",
        rationale_ru="??????? ????? ?????????.",
        asset_ids=("asset-1",),
    )

    missing = MissingEpisodeRC2(
        episode_id="episode-crema",
        event_type="crema",
        title_ru="???????? ?????",
        description_ru="????????? ???? ?????????.",
        coverage_status="MISSING",
        importance=0.95,
        required_visuals=(
            "monument burning at night",
            "firefighters near the monument",
        ),
        generation_recommended=True,
    )

    return VisualUnderstandingResultRC2(
        project_id="hogueras",
        topic="Hogueras de Alicante",
        source_assets_total=1,
        analyzed_assets_total=1,
        event_clusters=(cluster,),
        festival_chronology=(chronology,),
        off_topic_assets=(),
        missing_episodes=(missing,),
        asset_understanding=(make_asset(),),
    )


def test_result_contains_four_required_sections():
    result = make_result().to_dict()

    assert "event_clusters" in result
    assert "festival_chronology" in result
    assert "off_topic_assets" in result
    assert "missing_episodes" in result


def test_all_source_assets_must_be_analyzed():
    result = make_result()

    invalid = VisualUnderstandingResultRC2(
        project_id=result.project_id,
        topic=result.topic,
        source_assets_total=2,
        analyzed_assets_total=1,
        event_clusters=result.event_clusters,
        festival_chronology=result.festival_chronology,
        off_topic_assets=result.off_topic_assets,
        missing_episodes=result.missing_episodes,
        asset_understanding=result.asset_understanding,
    )

    with pytest.raises(
        ValueError,
        match="All source assets",
    ):
        invalid.validate()


def test_off_topic_asset_requires_evidence():
    item = OffTopicAssetRC2(
        asset_id="asset-cat",
        filename="cat.jpg",
        reason_ru="???????? ???????? ??? ????????? ?????????.",
        off_topic_score=0.97,
        detected_subject="cat",
    )

    result = item.to_dict()

    assert result["recommended_action"] == "EXCLUDE"


def test_missing_episode_requires_visual_requirements():
    episode = MissingEpisodeRC2(
        episode_id="missing-1",
        event_type="mascleta",
        title_ru="????????",
        description_ru="??????? ??????????????? ???.",
        coverage_status="MISSING",
        importance=0.9,
        required_visuals=(),
        generation_recommended=True,
    )

    with pytest.raises(
        ValueError,
        match="required_visuals",
    ):
        episode.validate()


def test_chronology_must_reference_known_cluster():
    result = make_result()

    invalid_entry = ChronologyEntryRC2(
        order=1,
        cluster_id="unknown-cluster",
        event_type="fireworks",
        title_ru="?????????",
        time_period="night",
        rationale_ru="?????? ?????.",
        asset_ids=("asset-1",),
    )

    invalid = VisualUnderstandingResultRC2(
        project_id=result.project_id,
        topic=result.topic,
        source_assets_total=1,
        analyzed_assets_total=1,
        event_clusters=result.event_clusters,
        festival_chronology=(invalid_entry,),
        off_topic_assets=(),
        missing_episodes=result.missing_episodes,
        asset_understanding=result.asset_understanding,
    )

    with pytest.raises(
        ValueError,
        match="unknown cluster",
    ):
        invalid.validate()


def test_off_topic_understanding_requires_high_score():
    asset = make_asset(
        asset_id="asset-foreign",
        relevance_status="OFF_TOPIC",
        off_topic_score=0.2,
    )

    with pytest.raises(
        ValueError,
        match="off_topic_score",
    ):
        asset.validate()
