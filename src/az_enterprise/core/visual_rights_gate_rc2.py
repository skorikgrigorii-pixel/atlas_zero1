
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class VisualRightsDecisionRC2:
    allowed: bool
    decision: str
    reason: str

    asset_id: str
    source_mode: str

    license_id: str
    author: str
    source_url: str
    license_url: str

    commercial_use: bool
    attribution_required: bool
    attribution_complete: bool

    final_render_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisualRightsGateRC2:
    """
    Conservative copyright/licensing gate for visual media.

    Automatic ALLOW:
      - internal / generated
      - Public Domain
      - CC0
      - CC BY with complete attribution metadata

    Automatic BLOCK:
      - CC BY-SA
      - CC BY-NC / NonCommercial
      - Editorial only
      - All Rights Reserved
      - Unknown / missing license
      - incomplete CC BY attribution
    """

    INTERNAL_MODES = {
        "GENERATED",
        "GEN",
        "INTERNAL",
        "OWNED",
        "ORIGINAL",
    }

    PUBLIC_DOMAIN_IDS = {
        "PUBLIC DOMAIN",
        "PUBLIC_DOMAIN",
        "PD",
        "PDM",
    }

    CC0_IDS = {
        "CC0",
        "CC ZERO",
        "CC ZERO 1.0",
        "CC0 1.0",
    }

    BLOCK_TOKENS = (
        "BY-SA",
        "BY SA",
        "NONCOMMERCIAL",
        "NON-COMMERCIAL",
        "BY-NC",
        "BY NC",
        "EDITORIAL",
        "ALL RIGHTS RESERVED",
        "ARR",
        "NO DERIVATIVES",
        "BY-ND",
        "BY ND",
    )

    def evaluate(
        self,
        *,
        asset_id: str,
        source_mode: str,
        license_id: str | None = None,
        author: str | None = None,
        source_url: str | None = None,
        license_url: str | None = None,
    ) -> VisualRightsDecisionRC2:

        asset_id = str(asset_id or "").strip()

        mode = str(
            source_mode or ""
        ).strip().upper()

        license_raw = str(
            license_id or ""
        ).strip()

        license_norm = (
            license_raw
            .upper()
            .replace("_", " ")
            .replace("-", "-")
        )

        author = str(
            author or ""
        ).strip()

        source_url = str(
            source_url or ""
        ).strip()

        license_url = str(
            license_url or ""
        ).strip()

        # -----------------------------------------------------
        # Internal / generated assets
        # -----------------------------------------------------

        if mode in self.INTERNAL_MODES:

            return VisualRightsDecisionRC2(
                allowed=True,
                decision="ALLOW",
                reason="internal_or_generated_asset",
                asset_id=asset_id,
                source_mode=mode,
                license_id="INTERNAL",
                author=author,
                source_url=source_url,
                license_url=license_url,
                commercial_use=True,
                attribution_required=False,
                attribution_complete=True,
                final_render_eligible=True,
            )

        # -----------------------------------------------------
        # Missing license
        # -----------------------------------------------------

        if not license_norm:

            return self._block(
                asset_id=asset_id,
                source_mode=mode,
                license_id=license_raw,
                author=author,
                source_url=source_url,
                license_url=license_url,
                reason="license_missing_or_unknown",
            )

        # -----------------------------------------------------
        # Explicitly disallowed license families
        # -----------------------------------------------------

        if any(
            token in license_norm
            for token in self.BLOCK_TOKENS
        ):

            return self._block(
                asset_id=asset_id,
                source_mode=mode,
                license_id=license_raw,
                author=author,
                source_url=source_url,
                license_url=license_url,
                reason="license_not_allowed_by_rc2_policy",
            )

        # -----------------------------------------------------
        # Public Domain
        # -----------------------------------------------------

        if (
            license_norm in self.PUBLIC_DOMAIN_IDS
            or "PUBLIC DOMAIN" in license_norm
        ):

            return VisualRightsDecisionRC2(
                allowed=True,
                decision="ALLOW",
                reason="public_domain",
                asset_id=asset_id,
                source_mode=mode,
                license_id=license_raw,
                author=author,
                source_url=source_url,
                license_url=license_url,
                commercial_use=True,
                attribution_required=False,
                attribution_complete=True,
                final_render_eligible=True,
            )

        # -----------------------------------------------------
        # CC0
        # -----------------------------------------------------

        if (
            license_norm in self.CC0_IDS
            or license_norm.startswith("CC0")
        ):

            return VisualRightsDecisionRC2(
                allowed=True,
                decision="ALLOW",
                reason="cc0",
                asset_id=asset_id,
                source_mode=mode,
                license_id=license_raw,
                author=author,
                source_url=source_url,
                license_url=license_url,
                commercial_use=True,
                attribution_required=False,
                attribution_complete=True,
                final_render_eligible=True,
            )

        # -----------------------------------------------------
        # CC BY only
        # -----------------------------------------------------

        is_cc_by = (
            license_norm.startswith("CC BY")
            or license_norm.startswith("CC-BY")
        )

        if is_cc_by:

            attribution_complete = all(
                (
                    author,
                    source_url,
                    license_url,
                )
            )

            if not attribution_complete:

                return self._block(
                    asset_id=asset_id,
                    source_mode=mode,
                    license_id=license_raw,
                    author=author,
                    source_url=source_url,
                    license_url=license_url,
                    reason="cc_by_attribution_incomplete",
                    attribution_required=True,
                )

            return VisualRightsDecisionRC2(
                allowed=True,
                decision="ALLOW",
                reason="cc_by_attribution_complete",
                asset_id=asset_id,
                source_mode=mode,
                license_id=license_raw,
                author=author,
                source_url=source_url,
                license_url=license_url,
                commercial_use=True,
                attribution_required=True,
                attribution_complete=True,
                final_render_eligible=True,
            )

        # -----------------------------------------------------
        # Anything else is unknown -> block
        # -----------------------------------------------------

        return self._block(
            asset_id=asset_id,
            source_mode=mode,
            license_id=license_raw,
            author=author,
            source_url=source_url,
            license_url=license_url,
            reason="unsupported_or_unverified_license",
        )

    def require_allowed(
        self,
        **kwargs: Any,
    ) -> VisualRightsDecisionRC2:

        decision = self.evaluate(
            **kwargs
        )

        if not decision.allowed:
            raise PermissionError(
                "VISUAL_RIGHTS_BLOCKED: "
                f"{decision.asset_id}: "
                f"{decision.reason}"
            )

        return decision

    @staticmethod
    def _block(
        *,
        asset_id: str,
        source_mode: str,
        license_id: str,
        author: str,
        source_url: str,
        license_url: str,
        reason: str,
        attribution_required: bool = False,
    ) -> VisualRightsDecisionRC2:

        attribution_complete = (
            bool(author)
            and bool(source_url)
            and bool(license_url)
        )

        return VisualRightsDecisionRC2(
            allowed=False,
            decision="BLOCK",
            reason=reason,
            asset_id=asset_id,
            source_mode=source_mode,
            license_id=license_id,
            author=author,
            source_url=source_url,
            license_url=license_url,
            commercial_use=False,
            attribution_required=attribution_required,
            attribution_complete=attribution_complete,
            final_render_eligible=False,
        )
