
from az_enterprise.core.visual_rights_gate_rc2 import (
    VisualRightsGateRC2,
)


def gate():
    return VisualRightsGateRC2()


def test_generated_asset_allowed():
    result = gate().evaluate(
        asset_id="GEN001",
        source_mode="GENERATED",
    )

    assert result.allowed is True
    assert result.final_render_eligible is True


def test_public_domain_allowed():
    result = gate().evaluate(
        asset_id="PD001",
        source_mode="REAL",
        license_id="Public Domain",
    )

    assert result.allowed is True
    assert result.commercial_use is True


def test_cc0_allowed():
    result = gate().evaluate(
        asset_id="CC0001",
        source_mode="REAL",
        license_id="CC0 1.0",
    )

    assert result.allowed is True


def test_cc_by_with_complete_attribution_allowed():
    result = gate().evaluate(
        asset_id="BY001",
        source_mode="REAL",
        license_id="CC BY 4.0",
        author="Example Author",
        source_url="https://example.org/file",
        license_url="https://creativecommons.org/licenses/by/4.0/",
    )

    assert result.allowed is True
    assert result.attribution_required is True
    assert result.attribution_complete is True


def test_cc_by_without_attribution_blocked():
    result = gate().evaluate(
        asset_id="BY002",
        source_mode="REAL",
        license_id="CC BY 4.0",
    )

    assert result.allowed is False
    assert result.reason == "cc_by_attribution_incomplete"


def test_cc_by_sa_blocked_by_conservative_policy():
    result = gate().evaluate(
        asset_id="SA001",
        source_mode="REAL",
        license_id="CC BY-SA 4.0",
        author="Author",
        source_url="https://example.org/file",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
    )

    assert result.allowed is False


def test_noncommercial_blocked():
    result = gate().evaluate(
        asset_id="NC001",
        source_mode="REAL",
        license_id="CC BY-NC 4.0",
    )

    assert result.allowed is False


def test_editorial_only_blocked():
    result = gate().evaluate(
        asset_id="ED001",
        source_mode="REAL",
        license_id="Editorial use only",
    )

    assert result.allowed is False


def test_unknown_license_blocked():
    result = gate().evaluate(
        asset_id="UNK001",
        source_mode="REAL",
        license_id="Unknown",
    )

    assert result.allowed is False


def test_missing_license_blocked():
    result = gate().evaluate(
        asset_id="UNK002",
        source_mode="REAL",
    )

    assert result.allowed is False


def test_require_allowed_raises():
    try:
        gate().require_allowed(
            asset_id="BAD001",
            source_mode="REAL",
            license_id="All Rights Reserved",
        )
    except PermissionError as exc:
        assert "VISUAL_RIGHTS_BLOCKED" in str(exc)
    else:
        raise AssertionError(
            "PermissionError was not raised"
        )
