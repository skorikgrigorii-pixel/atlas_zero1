from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .marketing_intelligence_rc1 import MarketingIntelligenceRC1
from .learning_core_rc1 import LearningCoreRC1


ANALYTICS_RECEIVED = "ANALYTICS_RECEIVED"
LEARNING_UPDATED = "LEARNING_UPDATED"


@dataclass
class FeedbackCycleResultRC1:
    project_id: str
    platform: str
    analytics_state: str
    learning_state: str
    profiles_ready: int
    events_emitted: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "atlas_zero.marketing_learning_feedback.rc1",
            "project_id": self.project_id,
            "platform": self.platform,
            "analytics_state": self.analytics_state,
            "learning_state": self.learning_state,
            "profiles_ready": self.profiles_ready,
            "events_emitted": list(self.events_emitted),
        }


class MarketingLearningBridgeRC1:
    """
    ATLAS ZERO — Marketing/Learning feedback bridge.

    Flow:

        analytics snapshot
              |
              v
        MarketingIntelligenceRC1
              |
              v
        performance summary
              |
              v
        LearningCoreRC1
              |
              v
        learning profiles
              |
              v
        Director AI advisory layer

    Important:
    - does not rewrite Director AI;
    - does not alter production policies;
    - does not bypass quality gates;
    - events are advisory signals only.
    """

    def __init__(
        self,
        *,
        db: Any,
        project_id: str,
        event_bus: Any | None = None,
    ) -> None:

        self.db = db
        self.project_id = str(project_id).strip()
        self.event_bus = event_bus

        if not self.project_id:
            raise ValueError("project_id is required")

        self.marketing = MarketingIntelligenceRC1(
            db=db,
            project_id=self.project_id,
        )

        self.learning = LearningCoreRC1(
            db=db,
            project_id=self.project_id,
        )

    def process_platform(
        self,
        platform: str,
    ) -> dict[str, Any]:

        performance = self.marketing.performance_summary(
            platform
        )

        emitted: list[str] = []

        self._emit(
            ANALYTICS_RECEIVED,
            {
                "project_id": self.project_id,
                "platform": platform,
                "performance": performance,
            },
        )

        emitted.append(ANALYTICS_RECEIVED)

        learning_result = self.learning.learn_from_performance(
            performance
        )

        if learning_result.get("state") == "LEARNING_UPDATED":

            profiles = self.learning.profiles(
                minimum_confidence=0.50
            )

            self._emit(
                LEARNING_UPDATED,
                {
                    "project_id": self.project_id,
                    "platform": platform,
                    "learning_result": learning_result,
                    "profiles": profiles,
                },
            )

            emitted.append(LEARNING_UPDATED)

        else:
            profiles = []

        result = FeedbackCycleResultRC1(
            project_id=self.project_id,
            platform=str(platform).lower(),
            analytics_state=str(
                performance.get("state")
            ),
            learning_state=str(
                learning_result.get("state")
            ),
            profiles_ready=len(profiles),
            events_emitted=emitted,
        )

        return result.to_dict()

    def director_advisory_payload(
        self,
        *,
        minimum_confidence: float = 0.60,
    ) -> dict[str, Any]:

        profiles = self.learning.profiles(
            minimum_confidence=minimum_confidence
        )

        return {
            "schema":
                "atlas_zero.director_learning_advisory.rc1",
            "project_id":
                self.project_id,
            "mode":
                "advisory_only",
            "minimum_confidence":
                minimum_confidence,
            "profiles":
                profiles,
            "profile_count":
                len(profiles),
            "authority":
                "LearningCoreRC1",
            "may_override_director":
                False,
            "may_modify_source":
                False,
            "may_bypass_quality_gate":
                False,
        }

    def process_all(
        self,
    ) -> dict[str, Any]:

        results = []

        for platform in (
            "youtube",
            "instagram",
            "tiktok",
        ):
            results.append(
                self.process_platform(platform)
            )

        advisory = self.director_advisory_payload()

        return {
            "schema":
                "atlas_zero.marketing_learning_cycle.rc1",
            "state":
                "MARKETING_LEARNING_CYCLE_COMPLETE",
            "project_id":
                self.project_id,
            "platform_results":
                results,
            "director_advisory":
                advisory,
        }

    # ------------------------------------------------------------------
    # Event adapter
    # ------------------------------------------------------------------

    def _emit(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:

        if self.event_bus is None:
            return

        emitter = getattr(
            self.event_bus,
            "emit",
            None,
        )

        if not callable(emitter):
            return

        # Canonical ATLAS ZERO RC2 EventBus contract:
        #
        # emit(
        #     event_type: str,
        #     payload: dict[str, Any] | None = None,
        # ) -> None
        #
        # Signature verified against active repository.

        emitter(
            event_name,
            payload,
        )
