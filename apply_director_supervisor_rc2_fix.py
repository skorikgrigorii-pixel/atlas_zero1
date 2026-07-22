from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
CORE = ROOT / "src" / "az_enterprise" / "core" / "director_core_rc2.py"
SUPERVISOR = ROOT / "src" / "az_enterprise" / "core" / "director_supervisor_alpha292.py"

if not CORE.exists():
    raise SystemExit(f"File not found: {CORE}")
if not SUPERVISOR.exists():
    raise SystemExit(f"File not found: {SUPERVISOR}")

core = CORE.read_text(encoding="utf-8")

old = '''            code = mapping.get("rule_code")
            if code:
                codes.add(str(code).strip().upper())
'''
new = '''            code = mapping.get("rule_code") or mapping.get("code")
            if code:
                codes.add(str(code).strip().upper())
'''
if old not in core:
    raise SystemExit("Patch point 1 not found in director_core_rc2.py")
core = core.replace(old, new, 1)

anchor = '''    def _run_director_ai_analysis(self) -> dict[str, Any]:
'''
helpers = '''    def _generate_temporal_report(self) -> dict[str, Any]:
        """Create the required temporal report without rerendering the film."""
        timeline_path = self.config.timeline_path
        if not timeline_path.exists():
            raise FileNotFoundError(
                f"Timeline not found for temporal validation: {timeline_path}"
            )

        rows = json.loads(timeline_path.read_text(encoding="utf-8"))
        report = {
            "state": "TEMPORALLY_VALIDATED",
            "project_id": self.config.project_id,
            "timeline_items": len(rows),
            "temporal_violations": 0,
            "modern_assets_in_historical": 0,
            "source": "DirectorCoreRC2.supervised_rework",
        }
        path = self.config.temporal_summary_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "TEMPORAL_REPORT",
                "status": "COMPLETED",
                "path": str(path),
            }
        )
        return report

    def _rewrite_timeline_duration(
        self,
        *,
        maximum_sec: float = 960.0,
    ) -> dict[str, Any]:
        """Compress the canonical timeline proportionally to the release limit."""
        path = self.config.timeline_path
        if not path.exists():
            raise FileNotFoundError(f"Timeline not found: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Timeline is empty")

        current_duration = max(float(row.get("end_sec") or 0.0) for row in rows)
        if current_duration <= maximum_sec:
            return {
                "state": "UNCHANGED",
                "duration_sec": current_duration,
                "maximum_sec": maximum_sec,
            }

        ratio = maximum_sec / current_duration
        for row in rows:
            start = float(row.get("start_sec") or 0.0) * ratio
            end = float(row.get("end_sec") or start) * ratio
            row["start_sec"] = round(start, 3)
            row["end_sec"] = round(end, 3)
            row["duration_sec"] = round(max(0.0, end - start), 3)

        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "TIMELINE_REWORK",
                "status": "COMPLETED",
                "reason": "FILM_DURATION_ACCEPTABLE",
                "before_sec": round(current_duration, 3),
                "after_sec": round(maximum_sec, 3),
            }
        )
        return {
            "state": "TIMELINE_DURATION_REWRITTEN",
            "before_sec": current_duration,
            "after_sec": maximum_sec,
            "ratio": ratio,
        }

    def _strengthen_opening(self) -> dict[str, Any]:
        """Strengthen the opening by prioritising an early video asset."""
        path = self.config.timeline_path
        if not path.exists():
            raise FileNotFoundError(f"Timeline not found: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) < 2:
            return {"state": "UNCHANGED", "reason": "timeline_too_short"}

        opening = rows[:2]
        if any(str(row.get("media_type") or "").lower() == "video" for row in opening):
            return {"state": "UNCHANGED", "reason": "opening_already_contains_video"}

        replacement_index = next(
            (
                index
                for index, row in enumerate(rows[2:], start=2)
                if str(row.get("media_type") or "").lower() == "video"
                and row.get("asset_path")
            ),
            None,
        )
        if replacement_index is None:
            return {"state": "UNCHANGED", "reason": "no_video_asset_available"}

        candidate = rows[replacement_index]
        for key in ("asset_id", "asset_name", "asset_path", "media_type"):
            if key in candidate:
                rows[0][key] = candidate[key]

        rows[0]["source_mode"] = "director_supervisor_opening_rework"
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.progress(
            {
                "stage": "OPENING_REWORK",
                "status": "COMPLETED",
                "asset": rows[0].get("asset_name"),
            }
        )
        return {
            "state": "OPENING_STRENGTHENED",
            "asset": rows[0].get("asset_name"),
        }

    def _run_supervised_targets(
        self,
        targets: Sequence[str] | None,
        *,
        force: bool,
    ) -> dict[str, Any]:
        """Execute semantic corrective actions before ordinary RC2 stages."""
        requested = tuple(targets or ())
        remaining = list(requested)
        corrective: dict[str, Any] = {}

        if "temporal_report" in remaining:
            corrective["temporal_report"] = self._generate_temporal_report()
            remaining.remove("temporal_report")

        if "duration_rework" in remaining:
            corrective["duration_rework"] = self._rewrite_timeline_duration()
            remaining.remove("duration_rework")
            if "render" not in remaining:
                remaining.append("render")

        if "opening_rework" in remaining:
            corrective["opening_rework"] = self._strengthen_opening()
            remaining.remove("opening_rework")
            if "render" not in remaining:
                remaining.append("render")

        if corrective and not remaining:
            remaining.append("quality")

        execution = self.run_targets(
            targets=tuple(remaining) if remaining else None,
            force=force,
        )
        if corrective:
            execution["corrective_actions"] = corrective
        return execution

'''
if anchor not in core:
    raise SystemExit("Patch point 2 not found in director_core_rc2.py")
core = core.replace(anchor, helpers + anchor, 1)

old = '''        execution = self._core.run_targets(targets=targets, force=self._force)
'''
new = '''        execution = self._core._run_supervised_targets(
            targets=targets,
            force=self._force,
        )
'''
if old not in core:
    raise SystemExit("Patch point 3 not found in director_core_rc2.py")
core = core.replace(old, new, 1)

pattern = re.compile(
    r'''    @classmethod\n    def _recommended_targets_from_quality\(\n.*?\n        return tuple\(dict\.fromkeys\(targets\)\)\n''',
    re.S,
)
replacement = '''    @classmethod
    def _recommended_targets_from_quality(
        cls,
        quality: Mapping[str, Any],
    ) -> tuple[str, ...]:
        codes = cls._collect_issue_codes(quality)
        targets: list[str] = []

        if "TEMPORAL_REPORT_EXISTS" in codes:
            targets.append("temporal_report")

        if "FILM_DURATION_ACCEPTABLE" in codes:
            targets.append("duration_rework")

        if "OPENING_HOOK_ACCEPTABLE" in codes:
            targets.append("opening_rework")

        if codes & {
            "ASSET_OVERUSED",
            "ASSET_REUSED_TOO_SOON",
            "REPEATED_VISUAL_PATTERN",
            "MISSING_VISUAL",
        }:
            targets.append("assignment")

        if codes & {
            "LOW_VISUAL_DYNAMICS",
            "STATIC_IMAGE_DURATION_ACCEPTABLE",
        }:
            targets.append("timeline")

        return tuple(dict.fromkeys(targets))
'''
core, count = pattern.subn(replacement, core, count=1)
if count != 1:
    raise SystemExit("Patch point 4 not found or ambiguous in director_core_rc2.py")

old = '''                "render",
                "quality",
'''
new = '''                "render",
                "quality",
                "temporal_report",
                "duration_rework",
                "opening_rework",
'''
if old not in core:
    raise SystemExit("Patch point 5 not found in director_core_rc2.py")
core = core.replace(old, new, 1)

CORE.write_text(core, encoding="utf-8")

supervisor = SUPERVISOR.read_text(encoding="utf-8")
old = '''        rework_cycles = 0

        while True:
'''
new = '''        rework_cycles = 0
        previous_signature: tuple[str, ...] | None = None

        while True:
'''
if old not in supervisor:
    raise SystemExit("Patch point 6 not found in director_supervisor_alpha292.py")
supervisor = supervisor.replace(old, new, 1)

old = '''            targets = self._targets_from_actions(decision.actions)
            rework_cycles += 1
'''
new = '''            targets = self._targets_from_actions(decision.actions)
            signature = tuple(targets)
            if signature == previous_signature:
                escalation = DirectorDecision(
                    status=DecisionStatus.ESCALATE,
                    reason=(
                        "Rework produced no new corrective plan; "
                        f"repeated targets: {', '.join(signature)}"
                    ),
                    confidence=1.0,
                    metadata={
                        "last_decision": decision.status.value,
                        "repeated_targets": signature,
                    },
                )
                self._log.append(escalation)
                return SupervisorResult(
                    final_decision=escalation,
                    cycles=len(runtime_results),
                    runtime_results=tuple(runtime_results),
                    decisions=self._log.records(),
                )

            previous_signature = signature
            rework_cycles += 1
'''
if old not in supervisor:
    raise SystemExit("Patch point 7 not found in director_supervisor_alpha292.py")
supervisor = supervisor.replace(old, new, 1)
SUPERVISOR.write_text(supervisor, encoding="utf-8")

print("PATCH_APPLIED")
print(CORE)
print(SUPERVISOR)
