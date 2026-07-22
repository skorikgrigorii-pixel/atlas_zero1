from types import SimpleNamespace

from az_enterprise.core.transition_engine_rc2 import (
    FFmpegTransitionGraphBuilder,
    TransitionEngineRC2,
)


def test_crossfade_profile():
    clip = SimpleNamespace(transition="crossfade", transition_duration_sec=0.6)
    profile = TransitionEngineRC2.build_profile(
        clip,
        left_duration_sec=3.0,
        right_duration_sec=4.0,
    )
    assert profile.enabled is True
    assert profile.ffmpeg_name == "fade"
    assert profile.duration_sec == 0.6


def test_cut_profile():
    clip = SimpleNamespace(transition="cut", transition_duration_sec=1.0)
    profile = TransitionEngineRC2.build_profile(
        clip,
        left_duration_sec=3.0,
        right_duration_sec=4.0,
    )
    assert profile.enabled is False
    assert profile.duration_sec == 0.0


def test_unknown_transition_falls_back_to_cut():
    clip = SimpleNamespace(transition="unknown_transition", transition_duration_sec=0.5)
    profile = TransitionEngineRC2.build_profile(
        clip,
        left_duration_sec=3.0,
        right_duration_sec=4.0,
    )
    assert profile.enabled is False
    assert profile.fallback_used is True


def test_xfade_graph_offsets():
    clips = [
        SimpleNamespace(transition="crossfade", transition_duration_sec=0.5),
        SimpleNamespace(transition="dissolve", transition_duration_sec=0.25),
    ]
    profiles = [
        TransitionEngineRC2.build_profile(
            clips[0], left_duration_sec=3.0, right_duration_sec=4.0
        ),
        TransitionEngineRC2.build_profile(
            clips[1], left_duration_sec=4.0, right_duration_sec=2.0
        ),
    ]
    graph, label, duration = FFmpegTransitionGraphBuilder.build(
        segment_durations=[3.0, 4.0, 2.0],
        profiles=profiles,
    )
    assert "offset=2.500000" in graph
    assert "offset=6.250000" in graph
    assert label == "[vxf2]"
    assert duration == 8.25
