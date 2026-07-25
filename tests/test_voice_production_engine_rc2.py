import json

import pytest

from az_enterprise.core.project_config_rc2 import (
    ProjectConfigRC2,
)
from az_enterprise.core.voice_production_engine_rc2 import (
    VoiceProductionEngineRC2,
)


def test_discovers_canonical_script(
    tmp_path,
):
    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    script_dir = (
        config.project_dir
        / "script"
    )

    script_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    script_path = (
        script_dir
        / "production_script.json"
    )

    script_path.write_text(
        json.dumps({
            "scenes": [],
        }),
        encoding="utf-8",
    )

    engine = VoiceProductionEngineRC2(
        config
    )

    assert (
        engine
        ._discover_production_script()
        == script_path
    )


def test_missing_script_is_rejected(
    tmp_path,
):
    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    engine = VoiceProductionEngineRC2(
        config
    )

    with pytest.raises(
        FileNotFoundError,
        match="Production script JSON",
    ):
        engine._discover_production_script()


def test_speech_rate_is_bounded(
    tmp_path,
):
    config = ProjectConfigRC2(
        project_id="sample",
        root_dir=tmp_path,
    )

    high = VoiceProductionEngineRC2(
        config,
        speech_rate=50,
    )

    low = VoiceProductionEngineRC2(
        config,
        speech_rate=-50,
    )

    assert high.speech_rate == 10
    assert low.speech_rate == -10
