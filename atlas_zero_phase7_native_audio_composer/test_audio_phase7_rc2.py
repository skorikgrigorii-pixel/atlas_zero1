from types import SimpleNamespace

from az_enterprise.core.audio_timeline_rc2 import AudioEventRC2
from az_enterprise.core.ducking_engine_rc2 import DuckingEngineRC2, DuckingProfileRC2
from az_enterprise.core.loudness_engine_rc2 import LoudnessEngineRC2, LoudnessProfileRC2


def test_audio_event_end():
    event = AudioEventRC2(
        event_id="voice_1",
        kind="voice",
        asset_path="dummy.wav",
        start_sec=2.0,
        duration_sec=3.5,
    )
    assert event.end_sec == 5.5


def test_ducking_filter():
    result = DuckingEngineRC2.build_filter(
        music_label="[music]",
        voice_label="[voice]",
        output_label="[ducked]",
        profile=DuckingProfileRC2(),
    )
    assert "sidechaincompress" in result
    assert result.endswith("[ducked]")


def test_loudness_filter():
    result = LoudnessEngineRC2.build_filter(
        "[mix]",
        "[final]",
        LoudnessProfileRC2(),
    )
    assert "loudnorm" in result
    assert "alimiter" in result
    assert result.endswith("[final]")
