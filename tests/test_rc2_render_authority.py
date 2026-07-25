from pathlib import Path


def test_render_engine_rc2_is_canonical_authority():
    source = Path(
        "src/az_enterprise/core/render_engine_rc2.py"
    ).read_text(encoding="utf-8")

    assert '"authority": "RenderEngineRC2"' in source
    assert '"backend": "RenderEngineRC1"' in source
    assert "root_dir=self.config.root_dir" in source
    assert "RENDER_COMPLETE" in source
    assert "self.probe(partial)" in source
    assert "os.replace(partial, destination)" in source


def test_rc1_is_used_only_as_backend_by_rc2():
    source = Path(
        "src/az_enterprise/core/render_engine_rc2.py"
    ).read_text(encoding="utf-8")

    assert "backend = RenderEngineRC1(" in source
    assert "report = backend.run()" in source
    assert "BACKEND_START" in source
    assert "BACKEND_COMPLETE" in source


def test_cli_exposes_canonical_rc2_render():
    source = Path(
        "src/az_enterprise/cli.py"
    ).read_text(encoding="utf-8")

    assert "'render-rc2'" in source
    assert "RenderEngineRC2(" in source
    assert "ProjectConfigRC2(" in source
    assert "use render-rc2 for canonical production runs" in source


def test_render_authority_does_not_change_missing_policy():
    rc2_source = Path(
        "src/az_enterprise/core/render_engine_rc2.py"
    ).read_text(encoding="utf-8")

    rc1_source = Path(
        "src/az_enterprise/core/render_engine_rc1.py"
    ).read_text(encoding="utf-8")

    assert "skipped_missing_assets" in rc1_source
    assert "_collect_assigned_clips" in rc1_source

    forbidden = (
        "TIMELINE_INCOMPLETE",
        "missing > 0",
        "incomplete > 0",
        "status != 'assigned'",
        'status != "assigned"',
    )

    for token in forbidden:
        assert token not in rc2_source
