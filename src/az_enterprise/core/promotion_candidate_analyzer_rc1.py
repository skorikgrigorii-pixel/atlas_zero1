from __future__ import annotations

import json
import math
import re

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .promotion_factory_rc1 import (
    PromotionCandidateRC1,
)

from .promotion_narration_alignment_rc1 import (
    PromotionNarrationAlignmentRC1,
)


@dataclass(frozen=True)
class PromotionCandidateScoreRC1:
    candidate_id: str
    start_sec: float
    end_sec: float
    duration_sec: float

    hook_score: float
    curiosity_score: float
    emotion_score: float
    visual_score: float
    standalone_score: float
    duration_score: float
    diversity_score: float

    # RC1 story-arc extension.
    # Defaults preserve compatibility for any external code constructing
    # PromotionCandidateScoreRC1 with the legacy contract.
    semantic_target_score: float = 0.0
    story_completeness_score: float = 0.0
    story_gate_passed: bool = True

    total_score: float = 0.0

    opening_text: str = ""
    story_summary: str = ""
    visual_summary: str = ""
    emotion_summary: str = ""

    first_shot_id: str = ""
    last_shot_id: str = ""
    shot_count: int = 0

    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromotionCandidateAnalyzerRC1:
    """
    ATLAS ZERO — Promotion Candidate Analyzer RC1.

    Authority:
        Timeline RC2 remains source authority.

    Purpose:
        Find strong self-contained excerpts from a completed film
        for YouTube Shorts, Instagram Reels and TikTok.

    This analyzer:
    - never rewrites the production script;
    - never invents new narration;
    - uses actual shot boundaries;
    - produces ranked candidates only;
    - delegates rendering to Promotion Factory / existing FFmpeg stack.
    """

    DEFAULT_MIN_DURATION_SEC = 18.0
    DEFAULT_TARGET_DURATION_SEC = 32.0
    DEFAULT_MAX_DURATION_SEC = 52.0

    # Strong opening / curiosity vocabulary.
    # Russian + English because ATLAS ZERO may produce multilingual films.
    HOOK_PATTERNS = (
        "?",
        "!",
        "почему",
        "как ",
        "что если",
        "никто",
        "никогда",
        "невозможно",
        "тайн",
        "загад",
        "исчез",
        "погиб",
        "последн",
        "единствен",
        "впервые",
        "неожидан",
        "запрещ",
        "секрет",
        "what if",
        "why ",
        "how ",
        "nobody",
        "never",
        "impossible",
        "mystery",
        "secret",
        "disappear",
        "last ",
        "first ",
    )

    CURIOSITY_PATTERNS = (
        "но ",
        "однако",
        "вопреки",
        "до сих пор",
        "неизвест",
        "никто не знает",
        "нет ответа",
        "странн",
        "необъяс",
        "парадокс",
        "след",
        "обнаруж",
        "версия",
        "легенд",
        "but ",
        "however",
        "unknown",
        "no answer",
        "unexplained",
        "strange",
        "legend",
        "discovered",
    )

    EMOTION_PATTERNS = (
        "страх",
        "ужас",
        "смерт",
        "гибел",
        "исчез",
        "отчаян",
        "надежд",
        "траг",
        "шок",
        "опас",
        "огонь",
        "лед",
        "бур",
        "свящ",
        "fear",
        "death",
        "disaster",
        "tragic",
        "shock",
        "danger",
        "fire",
        "ice",
        "sacred",
    )

    VISUAL_PATTERNS = (
        "aerial",
        "drone",
        "панорам",
        "общий план",
        "крупный план",
        "воздуш",
        "архив",
        "карта",
        "лед",
        "океан",
        "гора",
        "вершин",
        "огонь",
        "плам",
        "толпа",
        "шторм",
        "кораб",
        "экспед",
        "храм",
        "ритуал",
        "ноч",
        "sunset",
        "mountain",
        "ocean",
        "fire",
        "crowd",
        "storm",
        "ship",
        "temple",
        "ritual",
    )

    WEIGHTS = {
        "hook": 0.24,
        "curiosity": 0.18,
        "emotion": 0.14,
        "visual": 0.16,
        "standalone": 0.14,
        "duration": 0.09,
        "diversity": 0.05,
    }

    def __init__(
        self,
        *,
        project_id: str,
        root: str | Path,
        timeline_path: str | Path | None = None,
        narration_script_path: str | Path | None = None,
    ) -> None:

        self.project_id = str(
            project_id
        ).strip()

        if not self.project_id:
            raise ValueError(
                "project_id is required"
            )

        self.root = Path(root)

        self.timeline_path = (
            Path(timeline_path)
            if timeline_path is not None
            else (
                self.root
                / "workspace"
                / "exports"
                / self.project_id
                / "rc2"
                / "timeline"
                / "timeline.json"
            )
        )

        self.narration_script_path = (
            Path(narration_script_path)
            if narration_script_path is not None
            else None
        )

        self.output_dir = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "promotion"
        )

    # ------------------------------------------------------------------
    # Timeline loading
    # ------------------------------------------------------------------

    def load_timeline(
        self,
    ) -> list[dict[str, Any]]:

        if not self.timeline_path.is_file():
            raise FileNotFoundError(
                self.timeline_path
            )

        payload = json.loads(
            self.timeline_path.read_text(
                encoding="utf-8-sig"
            )
        )

        items = self._extract_items(
            payload
        )

        normalized = []

        for position, raw in enumerate(
            items,
            1,
        ):

            item = dict(raw)

            start = self._number(
                item.get(
                    "start_sec",
                    item.get(
                        "start",
                        item.get(
                            "timeline_start_sec"
                        ),
                    ),
                )
            )

            end = self._number(
                item.get(
                    "end_sec",
                    item.get(
                        "end",
                        item.get(
                            "timeline_end_sec"
                        ),
                    ),
                )
            )

            if start is None or end is None:
                continue

            if end <= start:
                continue

            shot_id = str(
                item.get(
                    "shot_id",
                    item.get(
                        "id",
                        f"{self.project_id}_shot_{position:04d}",
                    ),
                )
            )

            normalized.append({
                **item,
                "_shot_id":
                    shot_id,

                "_start_sec":
                    float(start),

                "_end_sec":
                    float(end),

                "_story":
                    self._text(
                        item,
                        (
                            "story_goal",
                            "story",
                            "narration",
                            "voice_text",
                            "text",
                            "description",
                        ),
                    ),

                "_visual":
                    self._text(
                        item,
                        (
                            "visual_need",
                            "visual",
                            "visual_description",
                            "asset_description",
                        ),
                    ),

                "_emotion":
                    self._text(
                        item,
                        (
                            "emotion",
                            "emotional_goal",
                            "mood",
                        ),
                    ),
            })

        normalized.sort(
            key=lambda item:
                (
                    item["_start_sec"],
                    item["_end_sec"],
                )
        )

        if not normalized:
            raise RuntimeError(
                "Timeline contains no usable timed shots"
            )

        return normalized

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        top_k: int = 3,
        min_duration_sec: float | None = None,
        target_duration_sec: float | None = None,
        max_duration_sec: float | None = None,
        maximum_overlap_ratio: float = 0.55,
        semantic_target: str | None = None,
        story_arc_mode: bool | None = None,
    ) -> dict[str, Any]:

        shots = self.load_timeline()

        narration_alignment = (
            PromotionNarrationAlignmentRC1(
                project_id=self.project_id,
                root=self.root,
                script_path=
                    self.narration_script_path,
            )
        )

        alignment_result = (
            narration_alignment.align()
        )

        narration_scenes = (
            alignment_result["scenes"]
        )

        minimum = float(
            min_duration_sec
            if min_duration_sec is not None
            else self.DEFAULT_MIN_DURATION_SEC
        )

        target = float(
            target_duration_sec
            if target_duration_sec is not None
            else self.DEFAULT_TARGET_DURATION_SEC
        )

        maximum = float(
            max_duration_sec
            if max_duration_sec is not None
            else self.DEFAULT_MAX_DURATION_SEC
        )

        if not (
            0 < minimum <= target <= maximum
        ):
            raise ValueError(
                "Expected 0 < minimum <= target <= maximum"
            )

        semantic_target_text = str(
            semantic_target or ""
        ).strip()

        use_story_arc = (
            bool(story_arc_mode)
            if story_arc_mode is not None
            else bool(semantic_target_text)
        )

        windows = self._build_windows(
            shots=shots,
            minimum=minimum,
            target=target,
            maximum=maximum,
        )

        scored = [
            self._score_window(
                window,
                target_duration_sec=target,
                narration_scenes=narration_scenes,
                semantic_target=semantic_target_text,
                story_arc_mode=use_story_arc,
            )
            for window in windows
        ]

        if use_story_arc:
            gated = [
                item
                for item in scored
                if item.story_gate_passed
            ]

            # Fail soft:
            # target-driven mode should not destroy legacy availability.
            # If no candidate passes the gate, retain all scored candidates
            # but their semantic/story scores remain visible for diagnosis.
            if gated:
                scored = gated

        scored.sort(
            key=lambda item:
                (
                    item.story_gate_passed
                    if use_story_arc
                    else True,

                    item.semantic_target_score
                    if use_story_arc
                    else item.total_score,

                    item.story_completeness_score
                    if use_story_arc
                    else item.hook_score,

                    item.total_score,
                    item.hook_score,
                    item.visual_score,
                ),
            reverse=True,
        )

        selected = self._deduplicate(
            scored,
            top_k=max(
                1,
                int(top_k),
            ),
            maximum_overlap_ratio=float(
                maximum_overlap_ratio
            ),
        )

        result = {
            "schema":
                "atlas_zero.promotion_candidates.rc1",

            "state":
                "PROMOTION_CANDIDATES_READY",

            "project_id":
                self.project_id,

            "timeline":
                str(
                    self.timeline_path.resolve()
                ),

            "semantic_source":
                "production_script_narrator_text",

            "alignment_source":
                alignment_result[
                    "alignment_source"
                ],

            "narration_scenes":
                len(narration_scenes),

            "narration_duration_sec":
                alignment_result[
                    "voice_duration_sec"
                ],

            "content_class":
                "FILM_PROMOTION",

            "selection_mode":
                (
                    "STORY_ARC"
                    if use_story_arc
                    else "DISCOVERY"
                ),

            "semantic_target":
                semantic_target_text,

            "story_gate_enabled":
                bool(use_story_arc),

            "production_target_per_platform":
                3,

            "shots_analyzed":
                len(shots),

            "candidate_windows":
                len(scored),

            "selected_candidates":
                len(selected),

            "duration_policy": {
                "minimum_sec":
                    minimum,

                "target_sec":
                    target,

                "maximum_sec":
                    maximum,
            },

            "weights":
                dict(self.WEIGHTS),

            "candidates": [
                item.to_dict()
                for item in selected
            ],
        }

        self.write_report(
            result
        )

        return result

    def promotion_candidates(
        self,
        result: dict[str, Any],
    ) -> list[PromotionCandidateRC1]:

        output = []

        for item in (
            result.get("candidates")
            or []
        ):

            output.append(
                PromotionCandidateRC1(
                    candidate_id=str(
                        item["candidate_id"]
                    ),

                    source_start_sec=float(
                        item["start_sec"]
                    ),

                    source_end_sec=float(
                        item["end_sec"]
                    ),

                    reason=str(
                        item.get(
                            "reason",
                            "",
                        )
                    ),
                )
            )

        return output

    # ------------------------------------------------------------------
    # Window generation
    # ------------------------------------------------------------------

    def _build_windows(
        self,
        *,
        shots: list[dict[str, Any]],
        minimum: float,
        target: float,
        maximum: float,
    ) -> list[list[dict[str, Any]]]:

        windows: list[
            list[dict[str, Any]]
        ] = []

        count = len(shots)

        for start_index in range(count):

            start_sec = shots[
                start_index
            ]["_start_sec"]

            current = []

            for end_index in range(
                start_index,
                count,
            ):

                current.append(
                    shots[end_index]
                )

                end_sec = shots[
                    end_index
                ]["_end_sec"]

                duration = (
                    end_sec - start_sec
                )

                if duration < minimum:
                    continue

                if duration > maximum:
                    break

                windows.append(
                    list(current)
                )

                # Once we are comfortably beyond the target,
                # do not create every possible longer version.
                if duration >= (
                    target + 8.0
                ):
                    break

        return windows

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_window(
        self,
        window: list[dict[str, Any]],
        *,
        target_duration_sec: float,
        narration_scenes: list[Any],
        semantic_target: str = "",
        story_arc_mode: bool = False,
    ) -> PromotionCandidateScoreRC1:

        first = window[0]
        last = window[-1]

        start_sec = float(
            first["_start_sec"]
        )

        end_sec = float(
            last["_end_sec"]
        )

        duration = (
            end_sec - start_sec
        )

        story_parts = self._narration_for_window(
            start_sec=start_sec,
            end_sec=end_sec,
            narration_scenes=narration_scenes,
        )

        # Editorial story_goal remains context only.
        editorial_context = [
            str(
                item.get(
                    "_story",
                    "",
                )
            ).strip()
            for item in window
            if str(
                item.get(
                    "_story",
                    "",
                )
            ).strip()
        ]

        visual_parts = [
            str(
                item.get(
                    "_visual",
                    "",
                )
            ).strip()
            for item in window
            if str(
                item.get(
                    "_visual",
                    "",
                )
            ).strip()
        ]

        emotion_parts = [
            str(
                item.get(
                    "_emotion",
                    "",
                )
            ).strip()
            for item in window
            if str(
                item.get(
                    "_emotion",
                    "",
                )
            ).strip()
        ]

        story = " ".join(
            story_parts
        )

        visual = " ".join(
            visual_parts
        )

        emotion = " ".join(
            emotion_parts
        )

        opening = (
            story_parts[0]
            if story_parts
            else visual_parts[0]
            if visual_parts
            else ""
        )

        hook_score = self._pattern_score(
            opening,
            self.HOOK_PATTERNS,
            base_for_nonempty=0.18,
        )

        curiosity_score = self._pattern_score(
            story,
            self.CURIOSITY_PATTERNS,
            base_for_nonempty=0.12,
        )

        emotion_score = self._emotion_score(
            emotion=emotion,
            story=story,
        )

        visual_score = self._pattern_score(
            visual,
            self.VISUAL_PATTERNS,
            base_for_nonempty=0.25,
        )

        standalone_score = (
            self._standalone_score(
                story=story,
                opening=opening,
                shot_count=len(window),
            )
        )

        duration_score = (
            self._duration_score(
                duration=duration,
                target=target_duration_sec,
            )
        )

        diversity_score = (
            self._diversity_score(
                story_parts
            )
        )

        semantic_target_score = (
            self._semantic_target_score(
                target=semantic_target,
                story=story,
                editorial_context=" ".join(
                    editorial_context
                ),
            )
            if story_arc_mode
            and semantic_target
            else 0.0
        )

        story_completeness_score = (
            self._story_completeness_score(
                story=story,
                story_parts=story_parts,
                editorial_context=editorial_context,
                shot_count=len(window),
            )
            if story_arc_mode
            else standalone_score
        )

        story_gate_passed = (
            self._story_arc_gate(
                semantic_target_score=
                    semantic_target_score,
                story_completeness_score=
                    story_completeness_score,
                story=story,
                story_parts=story_parts,
                shot_count=len(window),
            )
            if story_arc_mode
            else True
        )

        total = (
            hook_score
            * self.WEIGHTS["hook"]

            + curiosity_score
            * self.WEIGHTS["curiosity"]

            + emotion_score
            * self.WEIGHTS["emotion"]

            + visual_score
            * self.WEIGHTS["visual"]

            + standalone_score
            * self.WEIGHTS["standalone"]

            + duration_score
            * self.WEIGHTS["duration"]

            + diversity_score
            * self.WEIGHTS["diversity"]
        )

        if story_arc_mode:
            # Existing editorial quality remains useful, but target relevance
            # and narrative completeness become the dominant decision signals.
            total = (
                total * 0.40
                + semantic_target_score * 0.35
                + story_completeness_score * 0.25
            )

        candidate_id = (
            f"{self.project_id}"
            f"__promo_"
            f"{int(round(start_sec * 1000)):08d}_"
            f"{int(round(end_sec * 1000)):08d}"
        )

        reason = (
            "hook="
            f"{hook_score:.2f}; "
            "curiosity="
            f"{curiosity_score:.2f}; "
            "emotion="
            f"{emotion_score:.2f}; "
            "visual="
            f"{visual_score:.2f}; "
            "standalone="
            f"{standalone_score:.2f}; "
            "duration="
            f"{duration_score:.2f}; "
            "semantic_target="
            f"{semantic_target_score:.2f}; "
            "story_complete="
            f"{story_completeness_score:.2f}; "
            "story_gate="
            f"{int(story_gate_passed)}"
        )

        return PromotionCandidateScoreRC1(
            candidate_id=
                candidate_id,

            start_sec=
                start_sec,

            end_sec=
                end_sec,

            duration_sec=
                duration,

            hook_score=
                hook_score,

            curiosity_score=
                curiosity_score,

            emotion_score=
                emotion_score,

            visual_score=
                visual_score,

            standalone_score=
                standalone_score,

            duration_score=
                duration_score,

            diversity_score=
                diversity_score,

            semantic_target_score=
                semantic_target_score,

            story_completeness_score=
                story_completeness_score,

            story_gate_passed=
                story_gate_passed,

            total_score=
                total,

            opening_text=
                opening[:500],

            story_summary=
                story[:1500],

            visual_summary=
                visual[:1000],

            emotion_summary=
                emotion[:500],

            first_shot_id=
                str(
                    first["_shot_id"]
                ),

            last_shot_id=
                str(
                    last["_shot_id"]
                ),

            shot_count=
                len(window),

            reason=
                reason,
        )

    # ------------------------------------------------------------------
    # Component scores
    # ------------------------------------------------------------------

    @classmethod
    def _pattern_score(
        cls,
        text: str,
        patterns: tuple[str, ...],
        *,
        base_for_nonempty: float,
    ) -> float:

        normalized = str(
            text
        ).lower()

        if not normalized.strip():
            return 0.0

        matches = sum(
            1
            for pattern in patterns
            if pattern in normalized
        )

        score = (
            base_for_nonempty
            + matches * 0.16
        )

        # Numbers often work well as documentary hooks.
        if re.search(
            r"\b\d{2,}\b",
            normalized,
        ):
            score += 0.12

        return min(
            1.0,
            score,
        )

    @classmethod
    def _emotion_score(
        cls,
        *,
        emotion: str,
        story: str,
    ) -> float:

        explicit = cls._pattern_score(
            emotion,
            cls.EMOTION_PATTERNS,
            base_for_nonempty=0.35,
        )

        narrative = cls._pattern_score(
            story,
            cls.EMOTION_PATTERNS,
            base_for_nonempty=0.08,
        )

        return min(
            1.0,
            explicit * 0.65
            + narrative * 0.35,
        )

    @staticmethod
    def _standalone_score(
        *,
        story: str,
        opening: str,
        shot_count: int,
    ) -> float:

        if not story.strip():
            return 0.15

        words = re.findall(
            r"\w+",
            story,
            flags=re.UNICODE,
        )

        score = 0.35

        if len(words) >= 12:
            score += 0.15

        if len(words) >= 25:
            score += 0.12

        if shot_count >= 2:
            score += 0.10

        if shot_count >= 4:
            score += 0.08

        opening_lower = opening.lower()

        # Penalize openings that obviously depend on a previous sentence.
        weak_openings = (
            "поэтому",
            "таким образом",
            "и тогда",
            "после этого",
            "в результате",
            "therefore",
            "after that",
            "as a result",
        )

        if any(
            opening_lower.startswith(
                item
            )
            for item in weak_openings
        ):
            score -= 0.25

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )

    @staticmethod
    def _duration_score(
        *,
        duration: float,
        target: float,
    ) -> float:

        if target <= 0:
            return 0.0

        distance = abs(
            duration - target
        )

        score = (
            1.0
            - distance
            / max(
                target,
                1.0,
            )
        )

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )

    @staticmethod
    def _diversity_score(
        story_parts: list[str],
    ) -> float:

        if not story_parts:
            return 0.0

        normalized = {
            re.sub(
                r"\s+",
                " ",
                item.strip().lower(),
            )
            for item in story_parts
            if item.strip()
        }

        return min(
            1.0,
            len(normalized)
            / max(
                1,
                len(story_parts),
            ),
        )

    # ------------------------------------------------------------------
    # Candidate de-duplication
    # ------------------------------------------------------------------

    @classmethod
    def _deduplicate(
        cls,
        candidates:
            list[PromotionCandidateScoreRC1],
        *,
        top_k: int,
        maximum_overlap_ratio: float,
    ) -> list[PromotionCandidateScoreRC1]:

        selected = []

        for candidate in candidates:

            duplicate = False

            for existing in selected:

                overlap = cls._overlap_ratio(
                    candidate.start_sec,
                    candidate.end_sec,
                    existing.start_sec,
                    existing.end_sec,
                )

                semantic_similarity = (
                    cls._semantic_similarity(
                        candidate.story_summary,
                        existing.story_summary,
                    )
                )

                if (
                    overlap > maximum_overlap_ratio
                    or semantic_similarity >= 0.58
                ):
                    duplicate = True
                    break

            if duplicate:
                continue

            selected.append(
                candidate
            )

            if len(selected) >= top_k:
                break

        return selected

    @staticmethod
    def _semantic_tokens(
        value: str,
    ) -> set[str]:

        words = re.findall(
            r"[A-Za-z?-??-???0-9]+",
            str(value).lower(),
        )

        stop = {
            "?", "?", "??", "??", "?", "??",
            "?", "??", "??", "??", "??", "??",
            "??", "???", "??", "??", "???",
            "???", "???", "??", "???", "???",
            "??", "??", "???", "??", "??",
            "??", "?", "?", "??", "?",
            "the", "a", "an", "of", "and",
            "to", "in", "is", "that", "with",
            "for", "on", "from", "by",
            "this", "these", "those", "it",
            "as", "at", "was", "were", "be",
            "been", "are",
        }

        return {
            word
            for word in words
            if (
                len(word) >= 3
                and word not in stop
            )
        }


    @classmethod
    def _semantic_target_score(
        cls,
        *,
        target: str,
        story: str,
        editorial_context: str,
    ) -> float:

        target_tokens = cls._semantic_tokens(
            target
        )

        if not target_tokens:
            return 0.0

        candidate_tokens = cls._semantic_tokens(
            " ".join(
                (
                    story,
                    editorial_context,
                )
            )
        )

        if not candidate_tokens:
            return 0.0

        matched = (
            target_tokens
            & candidate_tokens
        )

        coverage = (
            len(matched)
            / len(target_tokens)
        )

        # Reward coverage of the requested concept.
        # Exact token repetition beyond target coverage
        # deliberately does not increase the score.
        return max(
            0.0,
            min(
                1.0,
                coverage,
            ),
        )


    @classmethod
    def _story_completeness_score(
        cls,
        *,
        story: str,
        story_parts: list[str],
        editorial_context: list[str],
        shot_count: int,
    ) -> float:

        text = str(story).strip()

        if not text:
            return 0.0

        tokens = cls._semantic_tokens(
            " ".join(
                [
                    text,
                    *editorial_context,
                ]
            )
        )

        word_count = len(
            re.findall(
                r"[A-Za-z?-??-???0-9]+",
                text,
            )
        )

        part_count = len(
            [
                item
                for item in story_parts
                if str(item).strip()
            ]
        )

        # Generic narrative-development signals.
        # These are language-level discourse markers,
        # not Film10 topic words.
        development_patterns = (
            "but ",
            "however",
            "then ",
            "after ",
            "before ",
            "because",
            "so ",
            "when ",
            "while ",
            "until ",
            "instead",
            "finally",
            "therefore",
            "yet ",
            "?? ",
            "??????",
            "?????",
            "????? ",
            "?? ????",
            "??????",
            "???????",
            "????? ",
            "???? ",
            "???????",
            "sin embargo",
            "pero ",
            "entonces",
            "despu?s",
            "antes ",
            "porque",
            "cuando ",
            "mientras",
            "hasta ",
            "finalmente",
            "por eso",
        )

        payoff_patterns = (
            "saved",
            "survived",
            "escaped",
            "destroyed",
            "collapsed",
            "reached",
            "became",
            "left ",
            "result",
            "meaning",
            "which meant",
            "that meant",
            "????",
            "?????",
            "?????",
            "??????",
            "??????",
            "??????",
            "??????",
            "???????",
            "??????",
            "salv",
            "sobreviv",
            "escap",
            "destr",
            "colaps",
            "alcanz",
            "resultado",
        )

        low = (
            " "
            + text.lower()
            + " "
        )

        development_hits = sum(
            1
            for pattern in development_patterns
            if pattern in low
        )

        payoff_hits = sum(
            1
            for pattern in payoff_patterns
            if pattern in low
        )

        lexical = min(
            1.0,
            len(tokens) / 38.0,
        )

        narration_span = min(
            1.0,
            word_count / 65.0,
        )

        multipart = min(
            1.0,
            part_count / 3.0,
        )

        visual_span = min(
            1.0,
            max(0, int(shot_count)) / 7.0,
        )

        development = min(
            1.0,
            development_hits / 2.0,
        )

        payoff = min(
            1.0,
            payoff_hits / 1.0,
        )

        score = (
            lexical * 0.15
            + narration_span * 0.15
            + multipart * 0.15
            + visual_span * 0.10
            + development * 0.20
            + payoff * 0.25
        )

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )


    @staticmethod
    def _story_arc_gate(
        *,
        semantic_target_score: float,
        story_completeness_score: float,
        story: str,
        story_parts: list[str],
        shot_count: int,
    ) -> bool:

        if semantic_target_score < 0.34:
            return False

        if story_completeness_score < 0.42:
            return False

        if len(story_parts) < 1:
            return False

        if int(shot_count) < 3:
            return False

        word_count = len(
            re.findall(
                r"[A-Za-z?-??-???0-9]+",
                str(story),
            )
        )

        if word_count < 18:
            return False

        return True


    @staticmethod
    def _semantic_similarity(
        left: str,
        right: str,
    ) -> float:

        def tokens(value: str) -> set[str]:

            words = re.findall(
                r"[A-Za-zА-Яа-яЁё0-9]+",
                str(value).lower(),
            )

            stop = {
                "и", "в", "во", "на", "с", "со",
                "к", "ко", "из", "по", "за", "от",
                "до", "для", "не", "но", "это",
                "как", "что", "он", "она", "они",
                "мы", "вы", "его", "ее", "её",
                "их", "у", "о", "об", "а",
                "the", "a", "an", "of", "and",
                "to", "in", "is", "that", "with",
                "for", "on", "from", "by",
            }

            return {
                word
                for word in words
                if (
                    len(word) >= 3
                    and word not in stop
                )
            }

        a = tokens(left)
        b = tokens(right)

        if not a or not b:
            return 0.0

        intersection = len(
            a & b
        )

        union = len(
            a | b
        )

        return (
            intersection / union
            if union
            else 0.0
        )


    @staticmethod
    def _overlap_ratio(
        a_start: float,
        a_end: float,
        b_start: float,
        b_end: float,
    ) -> float:

        overlap = max(
            0.0,
            min(a_end, b_end)
            - max(a_start, b_start),
        )

        if overlap <= 0:
            return 0.0

        shorter = min(
            a_end - a_start,
            b_end - b_start,
        )

        if shorter <= 0:
            return 0.0

        return overlap / shorter

    @staticmethod
    def _narration_for_window(
        *,
        start_sec: float,
        end_sec: float,
        narration_scenes: list[Any],
    ) -> list[str]:

        values = []

        for scene in narration_scenes:

            scene_start = float(
                scene["start_sec"]
            )

            scene_end = float(
                scene["end_sec"]
            )

            overlap = max(
                0.0,
                min(
                    end_sec,
                    scene_end,
                )
                - max(
                    start_sec,
                    scene_start,
                ),
            )

            if overlap <= 0:
                continue

            text = str(
                scene["text"]
            ).strip()

            if (
                text
                and text not in values
            ):
                values.append(
                    text
                )

        return values


    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def write_report(
        self,
        result: dict[str, Any],
    ) -> Path:

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            self.output_dir
            / "promotion_candidates_rc1.json"
        )

        path.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return path

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_items(
        payload: Any,
    ) -> list[dict[str, Any]]:

        if isinstance(
            payload,
            list,
        ):
            return [
                item
                for item in payload
                if isinstance(
                    item,
                    dict,
                )
            ]

        if not isinstance(
            payload,
            dict,
        ):
            return []

        for key in (
            "items",
            "shots",
            "timeline",
            "clips",
        ):

            value = payload.get(
                key
            )

            if isinstance(
                value,
                list,
            ):
                return [
                    item
                    for item in value
                    if isinstance(
                        item,
                        dict,
                    )
                ]

            if isinstance(
                value,
                dict,
            ):

                nested = (
                    PromotionCandidateAnalyzerRC1
                    ._extract_items(
                        value
                    )
                )

                if nested:
                    return nested

        return []

    @staticmethod
    def _text(
        item: dict[str, Any],
        keys: tuple[str, ...],
    ) -> str:

        parts = []

        for key in keys:

            value = item.get(
                key
            )

            if value is None:
                continue

            if isinstance(
                value,
                str,
            ):
                text = value.strip()

            elif isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):
                text = str(value)

            else:
                continue

            if (
                text
                and text not in parts
            ):
                parts.append(
                    text
                )

        return " ".join(
            parts
        )

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:

        if value is None:
            return None

        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if not math.isfinite(
            number
        ):
            return None

        return number
