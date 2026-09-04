from pathlib import Path
from datetime import datetime
import py_compile
import importlib.util
import shutil
import tempfile
import sqlite3
import sys
import re

ROOT = Path.cwd()

TARGET = (
    ROOT
    / "src"
    / "az_enterprise"
    / "core"
    / "generated_asset_store_rc2.py"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = TARGET.with_name(
    TARGET.name
    + ".before_continuity_winner_gate_"
    + STAMP
)

print("=" * 128)
print(
    "ATLAS ZERO - GENERATED ASSET CONTINUITY "
    "WINNER GATE RC2 INSTALLER"
)
print("=" * 128)

print(f"TARGET          : {TARGET}")
print("LIVE API        : 0")
print("PAID CALLS      : 0")
print()

# ============================================================================
# PRE-FLIGHT
# ============================================================================

print("-" * 128)
print("PRE-FLIGHT")
print("-" * 128)

if not TARGET.exists():
    raise FileNotFoundError(TARGET)

source = TARGET.read_text(
    encoding="utf-8-sig"
)

required_markers = [
    "class GeneratedAssetStoreRC2",
    "def record_review(",
    "def select_winner(",
    "temporal_score",
    "final_score",
    "selected_as_winner",
]

for marker in required_markers:
    if marker not in source:
        raise RuntimeError(
            f"Required marker missing: {marker}"
        )

print("GENERATED ASSET STORE : PASS")
print("REVIEW CONTRACT       : PASS")
print("WINNER CONTRACT       : PASS")

already_installed = (
    "ATLAS_ZERO_CONTINUITY_WINNER_GATE_RC2"
    in source
)

if already_installed:
    print("INSTALL STATE         : ALREADY INSTALLED")
else:
    print("INSTALL STATE         : PATCH REQUIRED")

# ============================================================================
# PATCH
# ============================================================================

if not already_installed:

    # ------------------------------------------------------------------------
    # Locate select_winner()
    # ------------------------------------------------------------------------

    match = re.search(
        r"(?m)^    def select_winner\(\n",
        source,
    )

    if not match:
        raise RuntimeError(
            "Cannot locate select_winner()"
        )

    insert_at = match.start()

    helper = r'''
    # ========================================================================
    # ATLAS_ZERO_CONTINUITY_WINNER_GATE_RC2
    # ========================================================================

    @staticmethod
    def _continuity_score_is_valid(
        temporal_score: object,
    ) -> bool:
        """
        A generated candidate may participate in winner selection
        only when its temporal continuity score is explicitly known
        and lies inside the canonical [0, 1] range.
        """

        if temporal_score is None:
            return False

        try:
            score = float(temporal_score)
        except (TypeError, ValueError):
            return False

        return 0.0 <= score <= 1.0

    @staticmethod
    def _continuity_review_is_compatible(
        review_json: object,
    ) -> bool:
        """
        Inspect canonical review metadata.

        Explicit continuity incompatibility is always blocking.
        Missing continuity metadata is not interpreted as proof
        of compatibility; temporal_score remains mandatory.
        """

        if review_json is None:
            return True

        if isinstance(review_json, str):

            if not review_json.strip():
                return True

            try:
                payload = json.loads(
                    review_json
                )
            except Exception:
                return True

        elif isinstance(review_json, dict):
            payload = review_json

        else:
            return True

        candidates = []

        if isinstance(payload, dict):

            candidates.append(payload)

            for key in (
                "continuity",
                "continuity_evaluation",
                "visual_continuity",
            ):
                value = payload.get(key)

                if isinstance(value, dict):
                    candidates.append(value)

        for item in candidates:

            if (
                "compatible" in item
                and item["compatible"] is False
            ):
                return False

            violations = item.get(
                "violations"
            )

            if isinstance(violations, list):

                for violation in violations:

                    if not isinstance(
                        violation,
                        dict,
                    ):
                        continue

                    if (
                        str(
                            violation.get(
                                "severity",
                                "",
                            )
                        ).upper()
                        == "BLOCK"
                    ):
                        return False

        return True

    def _require_candidate_continuity(
        self,
        candidate: object,
    ) -> None:
        """
        Final hard gate immediately before winner selection.

        This prevents a candidate from becoming ACCEPTED when:
        - temporal_score was never produced;
        - temporal_score is outside [0, 1];
        - review metadata explicitly marks continuity incompatible;
        - review metadata contains a BLOCK continuity violation.
        """

        temporal_score = candidate[
            "temporal_score"
        ]

        if not self._continuity_score_is_valid(
            temporal_score
        ):
            raise RuntimeError(
                "VISUAL_CONTINUITY_BLOCKED: "
                "candidate has no valid temporal_score"
            )

        if not self._continuity_review_is_compatible(
            candidate["review_json"]
        ):
            raise RuntimeError(
                "VISUAL_CONTINUITY_BLOCKED: "
                "candidate review contains an explicit "
                "continuity incompatibility"
            )

'''

    source = (
        source[:insert_at]
        + helper
        + source[insert_at:]
    )

    # ------------------------------------------------------------------------
    # Insert hard gate into existing select_winner()
    # immediately after existing review-status validation.
    # ------------------------------------------------------------------------

    status_block = re.search(
        r'''(?ms)
        (        if candidate\["status"\]\s+not\s+in\s+\{
        .*?
        ^            \)\n)
        ''',
        source,
        re.X,
    )

    if not status_block:
        raise RuntimeError(
            "Cannot locate select_winner "
            "status validation block"
        )

    gate_call = r'''

        # ------------------------------------------------------------
        # Canonical temporal / continuity winner gate.
        # A candidate cannot become ACCEPTED merely because it has
        # passed semantic/editorial review.
        # ------------------------------------------------------------

        self._require_candidate_continuity(
            candidate
        )
'''

    gate_pos = status_block.end()

    source = (
        source[:gate_pos]
        + gate_call
        + source[gate_pos:]
    )

# ============================================================================
# IN-MEMORY VALIDATION
# ============================================================================

print()
print("-" * 128)
print("IN-MEMORY VALIDATION")
print("-" * 128)

compile(
    source,
    str(TARGET),
    "exec",
)

markers = [
    "ATLAS_ZERO_CONTINUITY_WINNER_GATE_RC2",
    "_require_candidate_continuity",
    "_continuity_score_is_valid",
    "_continuity_review_is_compatible",
    "VISUAL_CONTINUITY_BLOCKED",
]

for marker in markers:
    if marker not in source:
        raise RuntimeError(
            f"Semantic marker missing: {marker}"
        )

print("PYTHON SYNTAX      : PASS")
print("SEMANTIC MARKERS   : PASS")

# ============================================================================
# ATOMIC INSTALL
# ============================================================================

print()
print("-" * 128)
print("ATOMIC INSTALL")
print("-" * 128)

if not already_installed:

    shutil.copy2(
        TARGET,
        BACKUP,
    )

    print(f"BACKUP             : {BACKUP}")

    tmp_target = TARGET.with_suffix(
        ".py.tmp"
    )

    tmp_target.write_text(
        source,
        encoding="utf-8",
        newline="\n",
    )

    tmp_target.replace(
        TARGET
    )

    print(f"WRITE              : {TARGET}")

else:

    print("WRITE              : SKIPPED")
    print("BACKUP             : NOT REQUIRED")

# ============================================================================
# COMPILE
# ============================================================================

print()
print("-" * 128)
print("POST-WRITE COMPILE")
print("-" * 128)

py_compile.compile(
    str(TARGET),
    doraise=True,
)

print("PY_COMPILE         : PASS")

# ============================================================================
# FRESH IMPORT
# ============================================================================

print()
print("-" * 128)
print("FRESH IMPORT")
print("-" * 128)

module_name = (
    "az_enterprise.core."
    "generated_asset_store_rc2"
)

if module_name in sys.modules:
    del sys.modules[module_name]

from az_enterprise.core.generated_asset_store_rc2 import (
    GeneratedAssetStoreRC2,
)

print("FRESH IMPORT       : PASS")

for symbol in (
    "_require_candidate_continuity",
    "_continuity_score_is_valid",
    "_continuity_review_is_compatible",
):

    if not hasattr(
        GeneratedAssetStoreRC2,
        symbol,
    ):
        raise RuntimeError(
            f"Runtime symbol missing: {symbol}"
        )

print("RUNTIME SYMBOLS    : PASS")

# ============================================================================
# PURE CONTRACT REGRESSION
# ============================================================================

print()
print("-" * 128)
print("STRICT CONTINUITY WINNER-GATE REGRESSION")
print("-" * 128)

assert (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(1.0)
)

assert (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(0.0)
)

assert (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(0.72)
)

assert not (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(None)
)

assert not (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(-0.1)
)

assert not (
    GeneratedAssetStoreRC2
    ._continuity_score_is_valid(1.1)
)

print("TEMPORAL SCORE RANGE       : PASS")
print("MISSING TEMPORAL SCORE     : BLOCK PASS")

compatible_review = {
    "continuity": {
        "compatible": True,
        "temporal_score": 0.92,
        "violations": [],
    }
}

assert (
    GeneratedAssetStoreRC2
    ._continuity_review_is_compatible(
        compatible_review
    )
)

incompatible_review = {
    "continuity": {
        "compatible": False,
        "temporal_score": 0.20,
        "violations": [
            {
                "code":
                    "ACTION_STATE_REGRESSION",
                "severity":
                    "BLOCK",
            }
        ],
    }
}

assert not (
    GeneratedAssetStoreRC2
    ._continuity_review_is_compatible(
        incompatible_review
    )
)

print("COMPATIBLE REVIEW          : PASS")
print("INCOMPATIBLE REVIEW        : BLOCK PASS")

block_review = {
    "visual_continuity": {
        "compatible": True,
        "violations": [
            {
                "code":
                    "DIRECTION_REVERSAL",
                "severity":
                    "BLOCK",
            }
        ],
    }
}

assert not (
    GeneratedAssetStoreRC2
    ._continuity_review_is_compatible(
        block_review
    )
)

print("BLOCK VIOLATION            : BLOCK PASS")

# ============================================================================
# FAKE ROW / FINAL HARD-GATE REGRESSION
# ============================================================================

class FakeCandidate(dict):
    pass


fake_store = object.__new__(
    GeneratedAssetStoreRC2
)

valid_candidate = FakeCandidate(
    temporal_score=0.95,
    review_json=(
        '{"continuity":'
        '{"compatible":true,'
        '"violations":[]}}'
    ),
)

fake_store._require_candidate_continuity(
    valid_candidate
)

print("VALID CANDIDATE            : PASS")

missing_score = FakeCandidate(
    temporal_score=None,
    review_json=None,
)

try:

    fake_store._require_candidate_continuity(
        missing_score
    )

except RuntimeError as exc:

    assert (
        "VISUAL_CONTINUITY_BLOCKED"
        in str(exc)
    )

else:

    raise RuntimeError(
        "Candidate without temporal_score "
        "was not blocked"
    )

print("NO TEMPORAL SCORE          : BLOCK PASS")

cooper_candidate = FakeCandidate(
    temporal_score=0.15,
    review_json=(
        '{"continuity":{'
        '"compatible":false,'
        '"violations":['
        '{"code":"ACTION_STATE_REGRESSION",'
        '"severity":"BLOCK"}'
        ']}}'
    ),
)

try:

    fake_store._require_candidate_continuity(
        cooper_candidate
    )

except RuntimeError as exc:

    assert (
        "VISUAL_CONTINUITY_BLOCKED"
        in str(exc)
    )

else:

    raise RuntimeError(
        "Cooper action reversal candidate "
        "was not blocked"
    )

print("COOPER ACTION REVERSAL     : BLOCK PASS")

# ============================================================================
# SOURCE-FLOW ASSERTIONS
# ============================================================================

print()
print("-" * 128)
print("SOURCE FLOW ASSERTIONS")
print("-" * 128)

disk_source = TARGET.read_text(
    encoding="utf-8-sig"
)

winner_pos = disk_source.find(
    "def select_winner("
)

if winner_pos < 0:
    raise RuntimeError(
        "select_winner missing after install"
    )

winner_tail = disk_source[
    winner_pos:
    winner_pos + 5000
]

if (
    "self._require_candidate_continuity("
    not in winner_tail
):
    raise RuntimeError(
        "Continuity gate is not connected "
        "to select_winner()"
    )

gate_call_pos = winner_tail.find(
    "self._require_candidate_continuity("
)

accept_pos = winner_tail.find(
    "status='ACCEPTED'"
)

if accept_pos < 0:
    raise RuntimeError(
        "ACCEPTED state mutation not found"
    )

if gate_call_pos > accept_pos:
    raise RuntimeError(
        "Continuity gate executes after ACCEPTED mutation"
    )

print("select_winner -> gate      : PASS")
print("gate -> ACCEPTED mutation  : PASS")

# ============================================================================
# FINAL ROUND-TRIP
# ============================================================================

compile(
    disk_source,
    str(TARGET),
    "exec",
)

print("DISK ROUND-TRIP            : PASS")

# ============================================================================
# REPORT
# ============================================================================

REPORT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / "_system"
    / "generated_asset_continuity_winner_gate_rc2"
)

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT = (
    REPORT_DIR
    / "GENERATED_ASSET_CONTINUITY_WINNER_GATE_RC2_INSTALL_REPORT.txt"
)

report_text = f"""
ATLAS ZERO - GENERATED ASSET CONTINUITY WINNER GATE RC2

TARGET:
{TARGET}

BACKUP:
{BACKUP if not already_installed else "NOT REQUIRED"}

RESULTS:
- temporal_score required before winner selection
- temporal_score range [0,1] enforced
- explicit continuity incompatible blocks winner
- BLOCK continuity violation blocks winner
- gate executes before ACCEPTED mutation
- Cooper action reversal regression blocked
- legacy GeneratedAssetStoreRC2 preserved
- API calls: 0
- paid calls: 0

STATUS:
PASS
""".strip()

REPORT.write_text(
    report_text,
    encoding="utf-8",
)

print()
print("=" * 128)
print(
    "ATLAS ZERO - GENERATED ASSET CONTINUITY "
    "WINNER GATE RC2 RESULT"
)
print("=" * 128)

print("GeneratedAssetStoreRC2       : PASS")
print("TEMPORAL SCORE REQUIRED      : PASS")
print("TEMPORAL SCORE RANGE         : PASS")
print("CONTINUITY COMPATIBILITY     : PASS")
print("BLOCK VIOLATION GATE         : PASS")
print("COOPER ACTION REVERSAL       : BLOCK PASS")
print("WINNER -> CONTINUITY GATE    : PASS")
print("GATE BEFORE ACCEPTED         : PASS")
print("PY_COMPILE                   : PASS")
print("FRESH IMPORT                 : PASS")
print("DISK ROUND-TRIP              : PASS")
print()
print(
    "CODE MODIFIED                : "
    + (
        "NO - ALREADY INSTALLED"
        if already_installed
        else "YES"
    )
)
print("API CALLS                    : 0")
print("PAID CALLS                   : 0")
print()
print(f"REPORT                       : {REPORT}")
print()
print(
    "STATUS : PASS - GENERATED VISUAL WINNER "
    "CANNOT BYPASS CONTINUITY"
)
print()
print(
    "NEXT : FILM 08 VISUAL DIRECTOR MAP"
)
print("=" * 128)
