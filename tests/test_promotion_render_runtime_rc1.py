from pathlib import Path

import pytest

from az_enterprise.core.promotion_render_runtime_rc1 import (
    PromotionRenderRuntimeRC1,
)

from az_enterprise.core.render_engine_rc2 import (
    RenderEngineRC2,
)


def make_master(
    root: Path,
    project_id: str = "franklin",
) -> Path:

    path = (
        root
        / "workspace"
        / "exports"
        / project_id
        / "rc2"
        / "render"
        / f"{project_id}_RC2.mp4"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_bytes(
        b"fake-master"
    )

    return path


def test_default_master_contract(
    tmp_path: Path,
):

    master = make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
    )

    assert (
        runtime.validate_source()
        == master
    )


def test_build_vertical_spec(
    tmp_path: Path,
):

    make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
    )

    spec = runtime.build_spec(
        candidate_id="promo_001",
        source_start_sec=10.0,
        source_end_sec=40.0,
    )

    assert spec.duration_sec == 30.0
    assert spec.width == 1080
    assert spec.height == 1920

    assert (
        spec.output_path.name
        == "promo_001.mp4"
    )


def test_prepare_limits_to_three(
    tmp_path: Path,
):

    make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
    )

    candidates = [
        {
            "candidate_id": f"promo_{i}",
            "source_start_sec":
                float(i * 10),
            "source_end_sec":
                float(i * 10 + 20),
        }
        for i in range(5)
    ]

    specs = runtime.prepare(
        candidates,
    )

    assert len(specs) == 3


def test_invalid_range_rejected(
    tmp_path: Path,
):

    make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
    )

    with pytest.raises(
        ValueError
    ):
        runtime.build_spec(
            candidate_id="bad",
            source_start_sec=20.0,
            source_end_sec=10.0,
        )


def test_missing_master_rejected(
    tmp_path: Path,
):

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
    )

    with pytest.raises(
        FileNotFoundError
    ):
        runtime.validate_source()


def test_render_command_uses_vertical_policy(
    tmp_path: Path,
):

    make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
        ffmpeg_path="ffmpeg-test",
    )

    spec = runtime.build_spec(
        candidate_id="promo_vertical",
        source_start_sec=25.0,
        source_end_sec=55.0,
    )

    command = runtime.build_render_command(
        spec
    )

    joined = " ".join(
        command
    )

    assert command[0] == "ffmpeg-test"

    assert "-ss" in command
    assert "-t" in command

    assert (
        "scale=1080:1920:"
        in joined
    )

    assert (
        "crop=1080:1920"
        in joined
    )

    assert "boxblur=20:1" in joined
    assert "overlay=" in joined

    assert "libx264" in command
    assert "aac" in command

    assert "0:a?" in command


def test_render_spec_uses_rc2_ffmpeg_executor(
    tmp_path: Path,
    monkeypatch,
):

    make_master(
        tmp_path
    )

    runtime = PromotionRenderRuntimeRC1(
        project_id="franklin",
        root=tmp_path,
        ffmpeg_path="ffmpeg-test",
    )

    spec = runtime.build_spec(
        candidate_id="promo_executor",
        source_start_sec=10.0,
        source_end_sec=40.0,
    )

    calls = []

    def fake_run_ffmpeg(
        command,
        *,
        step,
    ):
        calls.append(
            {
                "command": command,
                "step": step,
            }
        )

        output = Path(
            command[-1]
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_bytes(
            b"fake-promotion-master"
        )

    monkeypatch.setattr(
        RenderEngineRC2,
        "_run_ffmpeg",
        staticmethod(
            fake_run_ffmpeg
        ),
    )

    output = runtime.render_spec(
        spec
    )

    assert output.is_file()

    assert (
        output.read_bytes()
        == b"fake-promotion-master"
    )

    assert len(calls) == 1

    assert (
        "Promotion vertical master"
        in calls[0]["step"]
    )

