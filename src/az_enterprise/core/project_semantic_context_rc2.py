from __future__ import annotations
from collections import Counter

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .external_script_importer_rc2 import ExternalScriptImporterRC2


@dataclass(frozen=True)
class ProjectSemanticContextRC2:
    project_id: str
    title: str
    source_path: str | None
    event_labels: dict[str, tuple[str, ...]]
    topic_labels: dict[str, tuple[str, ...]]
    location_hint: str | None
    concepts: tuple[str, ...]


class ProjectSemanticContextBuilderRC2:
    """
    Build project-specific semantic vocabulary from the approved production
    script.

    This module is documentary-project independent. It must never contain
    vocabulary belonging to one specific film.
    """

    SCRIPT_CANDIDATES = (
        "script/approved_external_script.md",
        "script/approved_external_script.txt",
        "approved_external_script.md",
        "approved_external_script.txt",
    )

    STOPWORDS = {
        # Russian
        "который", "которая", "которые", "этого", "этот", "эта", "эти",
        "было", "были", "была", "будет", "может", "только", "после",
        "перед", "через", "между", "здесь", "тогда", "сейчас", "если",
        "потому", "чтобы", "когда", "очень", "даже", "того", "есть",
        "один", "одна", "несколько", "своего", "своей", "своих",
        "которого", "которой", "которых", "почему", "ничего",
        "нашего", "нашей", "этой", "этом", "этим",

        # English
        "about", "after", "again", "against", "before", "being",
        "between", "could", "every", "first", "from", "have", "into",
        "other", "their", "there", "these", "they", "this", "those",
        "through", "under", "very", "what", "when", "where", "which",
        "while", "with", "would", "your",
    }

    def __init__(
        self,
        project_id: str,
        root_dir: str | Path = ".",
    ) -> None:
        self.project_id = str(project_id)
        self.root_dir = Path(root_dir)
        self.project_dir = (
            self.root_dir
            / "workspace"
            / "projects"
            / self.project_id
        )

    def build(self) -> ProjectSemanticContextRC2:
        """
        Build semantic context using the strongest available canonical source.

        Source priority:
        1. approved external production script;
        2. canonical story_scenes stored in the ATLAS ZERO database;
        3. conservative generic fallback.

        The canonical DB path is intentionally project-independent. It allows
        projects created inside ATLAS ZERO to receive project-specific semantic
        vocabulary even when they do not have an approved_external_script file.
        """
        source = self._discover_script()

        if source is not None:
            context = self._build_from_approved_script(source)

            if context is not None:
                return context

        context = self._build_from_canonical_story()

        if context is not None:
            return context

        return self._fallback_context()

    def _build_from_approved_script(
        self,
        source: Path,
    ) -> ProjectSemanticContextRC2 | None:
        text = source.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        importer = ExternalScriptImporterRC2(
            project_id=self.project_id,
        )

        parsed_title, scenes = importer._parse(
            text,
            suffix=source.suffix.lower(),
        )

        title = (
            str(parsed_title or "").strip()
            or self._extract_title(text)
        )

        if not scenes:
            return None

        records: list[dict[str, str]] = []

        for scene in scenes:
            scene_id = str(scene.scene_id or "").strip()

            scene_title = str(scene.title or "").strip()

            narration = re.sub(
                r"\s+",
                " ",
                str(scene.narration_ru or "").strip(),
            )

            records.append(
                {
                    "scene_id": scene_id,
                    "title": scene_title,
                    "narration": narration,
                    "visual_strategy": "",
                }
            )

        return self._context_from_scene_records(
            title=title,
            records=records,
            source_path=str(source),
        )

    def _canonical_db_path(self) -> Path:
        return (
            self.root_dir
            / "workspace"
            / "atlas_zero_enterprise.sqlite3"
        )

    def _canonical_project_title(
        self,
        conn: sqlite3.Connection,
    ) -> str:
        try:
            row = conn.execute(
                """
                SELECT title
                FROM projects
                WHERE id=?
                LIMIT 1
                """,
                (self.project_id,),
            ).fetchone()
        except sqlite3.Error:
            row = None

        if row is not None:
            value = str(row[0] or "").strip()

            if value:
                return value

        return self.project_id.replace("_", " ").strip()

    def _build_from_canonical_story(
        self,
    ) -> ProjectSemanticContextRC2 | None:
        db_path = self._canonical_db_path()

        if not db_path.is_file():
            return None

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            try:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        idx,
                        block,
                        title,
                        narrative_goal,
                        emotional_goal,
                        visual_strategy
                    FROM story_scenes
                    WHERE project_id=?
                    ORDER BY idx
                    """,
                    (self.project_id,),
                ).fetchall()

                title = self._canonical_project_title(conn)

            finally:
                conn.close()

        except sqlite3.Error:
            return None

        if not rows:
            return None

        records: list[dict[str, str]] = []

        for row in rows:
            narration = re.sub(
                r"\s+",
                " ",
                str(row["narrative_goal"] or "").strip(),
            )

            if not narration:
                continue

            raw_title = str(row["title"] or "").strip()

            # Generic imported editorial buckets are not semantic scene names.
            if raw_title.upper() in {
                "",
                "GENERAL_CONTEXT",
                "DOCUMENTARY_CONTEXT",
                "PROJECT_CONTEXT",
            }:
                raw_title = ""

            records.append(
                {
                    "scene_id": str(row["id"] or row["idx"]),
                    "title": raw_title,
                    "narration": narration,
                    "visual_strategy": str(
                        row["visual_strategy"] or ""
                    ).strip(),
                }
            )

        if not records:
            return None

        return self._context_from_scene_records(
            title=title,
            records=records,
            source_path="canonical_db:story_scenes",
        )

    def _scene_semantic_phrase(
        self,
        narration: str,
    ) -> str:
        """
        Produce a compact project-independent visual phrase from narration.

        This is deliberately deterministic and local. It does not call an LLM
        and does not contain vocabulary belonging to any specific film.
        """
        clean = re.sub(
            r"\s+",
            " ",
            str(narration or "").strip(),
        )

        if not clean:
            return "documentary scene"

        concepts = self._extract_concepts(clean)

        if concepts:
            phrase = ", ".join(concepts[:8])
            return phrase[:220]

        return clean[:220]

    def _context_from_scene_records(
        self,
        *,
        title: str,
        records: list[dict[str, str]],
        source_path: str,
    ) -> ProjectSemanticContextRC2:
        corpus_text = " ".join(
            record["narration"]
            for record in records
            if record.get("narration")
        )

        concepts = self._extract_concepts(corpus_text)

        event_labels: dict[str, tuple[str, ...]] = {}

        for index, record in enumerate(records, start=1):
            narration = str(
                record.get("narration") or ""
            ).strip()

            if not narration:
                continue

            semantic_phrase = self._scene_semantic_phrase(
                narration
            )

            scene_title = str(
                record.get("title") or ""
            ).strip()

            label = "scene_{:03d}".format(index)

            prompt_subject = (
                scene_title
                if scene_title
                else semantic_phrase
            )

            narration_excerpt = narration[:260]

            event_labels[label] = (
                f"documentary image or footage specifically showing "
                f"{prompt_subject}",
                f"factual visual evidence directly matching "
                f"{semantic_phrase}",
                f"visual material matching this documentary passage: "
                f"{narration_excerpt}",
            )

        # Project-wide classes remain useful, but they are deliberately
        # secondary to the individual scene classes above.
        concept_text = ", ".join(concepts[:16])

        event_labels["project_context"] = (
            f"visual material directly related to the documentary {title}",
            f"factual visual evidence connected with {concept_text}",
            f"a documentary scene belonging to the subject of {title}",
        )

        event_labels["generic_context"] = (
            "general factual documentary context",
            "scientific geographical archival infrastructure landscape "
            "or human documentary material",
        )

        event_labels["unrelated_private_content"] = (
            "a private selfie family photograph or personal everyday scene",
            "an unrelated household object pet food car or private material",
            "visual material with no relationship to the current documentary",
        )

        topic_labels = self._build_topic_labels(
            concepts=concepts,
            title=title,
        )

        return ProjectSemanticContextRC2(
            project_id=self.project_id,
            title=title,
            source_path=source_path,
            event_labels=event_labels,
            topic_labels=topic_labels,
            location_hint=self._derive_location_hint(
                title,
                concepts,
            ),
            concepts=tuple(concepts),
        )
    def _discover_script(self) -> Path | None:
        for relative in self.SCRIPT_CANDIDATES:
            candidate = self.project_dir / relative
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _extract_title(text: str) -> str:
        for line in text.splitlines():
            value = line.strip()
            if not value:
                continue

            value = re.sub(
                r"^#{1,6}\s*",
                "",
                value,
            ).strip()

            if value:
                return value[:160]

        return "Documentary project"

    def _extract_concepts(
        self,
        text: str,
    ) -> list[str]:
        """
        Extract visually useful documentary concepts without project-specific
        vocabulary.

        The extractor intentionally prefers:
        - named/proper entities;
        - recurring concrete nouns;
        - recurring two- and three-word phrases;
        - geographical/scientific/institutional terms.

        It suppresses:
        - production markers;
        - narration glue;
        - pronouns and discourse words;
        - generic storytelling verbs/adverbs;
        - isolated numbers and timing language.

        This method is deterministic and local.
        """

        cleaned = str(text or "")

        # Production structure must never become visual semantics.
        cleaned = re.sub(
            r"\b(?:БЛОК|BLOCK)\s*\d+\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\b(?:ФИНАЛ|FINAL|HOOK|OPENING|SHOCK)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"[`*_>#\[\](){}|]",
            " ",
            cleaned,
        )

        cleaned = re.sub(r"\s+", " ", cleaned)

        noise = self.STOPWORDS | {
            # Russian discourse / narration glue
            "кто-то", "что-то", "где-то", "когда-то",
            "почему-то", "какой-то", "какая-то", "какие-то",
            "иногда", "наверное", "поэтому", "возможно",
            "невозможно", "особенно", "довольно",
            "действительно", "просто", "снова", "теперь",
            "потом", "пока", "сначала", "именно",
            "кажется", "оказалось", "оказаться",
            "становится", "становиться", "стало",
            "бывает", "быть", "можно", "нужно",
            "увидеть", "видеть", "знать", "сказать",
            "говорить", "делать", "найти", "оставаться",
            "появиться", "происходит", "произошло",
            "происходило", "начинается", "началось",
            "начали", "начинают", "продолжает",
            "продолжали", "оказался", "оказалась",
            "иметь", "имеет", "имело", "значение",
            "вместе", "среди", "через", "внутри",
            "внизу", "вверх", "вниз", "выше", "ниже",
            "рядом", "далеко", "почти", "более",
            "несколько", "много", "многие", "других",
            "другой", "новые", "новый", "новая",
            "первый", "первые", "последний",
            "обычный", "обычно", "сегодня",
            "утром", "вечером", "день", "дней",
            "время", "минут", "минуты", "секунд",
            "годы", "годами", "году",
            "человек", "люди", "людей",
            "который", "которая", "которые",
            "этого", "этой", "этом",
            "такой", "такая", "такие",
            "своей", "своих", "своего",
            "этот", "эта", "эти",
            "того", "тому",
            "здесь", "туда", "отсюда",
            "всего", "самого", "самой",
            "часть", "целую", "целый",
            "случилось", "случае",
            "вопрос", "история", "истории",
            "картина", "названия",
            "записи", "запись",
            "кадры", "кадр",
            "материал", "материала",
            "фильм", "фильма",
            "atlas", "zero",

            # English discourse glue
            "someone", "something", "somewhere",
            "sometimes", "perhaps", "maybe",
            "really", "already", "still",
            "again", "then", "now",
            "today", "yesterday", "tomorrow",
            "people", "person", "time",
            "minute", "minutes", "second", "seconds",
            "story", "film", "documentary",
            "footage", "image", "images",
            "video", "scene", "scenes",
        }

        token_pattern = (
            r"[A-Za-zА-Яа-яЁёÀ-ÿ]"
            r"[A-Za-zА-Яа-яЁёÀ-ÿ0-9\-]{2,}"
        )

        raw_tokens = re.findall(
            token_pattern,
            cleaned,
        )

        def normalize(value: str) -> str:
            return value.lower().strip("-")

        def usable(value: str) -> bool:
            n = normalize(value)

            if len(n) < 4:
                return False

            if n in noise:
                return False

            if n.isdigit():
                return False

            return True

        frequency: Counter[str] = Counter()
        display: dict[str, str] = {}
        proper_bonus: Counter[str] = Counter()

        for token in raw_tokens:
            if not usable(token):
                continue

            key = normalize(token)

            frequency[key] += 1
            display.setdefault(key, token)

            # Repeated capitalisation is useful evidence for names,
            # institutions and geographical entities.
            if token[:1].isupper():
                proper_bonus[key] += 1

        phrase_frequency: Counter[str] = Counter()
        phrase_display: dict[str, str] = {}
        phrase_proper_bonus: Counter[str] = Counter()

        # Two- and three-token windows are substantially more useful
        # for CLIP-like models than isolated generic words.
        for width in (2, 3):
            for index in range(
                0,
                max(0, len(raw_tokens) - width + 1),
            ):
                window = raw_tokens[
                    index:index + width
                ]

                if not all(usable(x) for x in window):
                    continue

                normalized = [
                    normalize(x)
                    for x in window
                ]

                key = " ".join(normalized)
                shown = " ".join(window)

                phrase_frequency[key] += 1
                phrase_display.setdefault(
                    key,
                    shown,
                )

                if any(
                    token[:1].isupper()
                    for token in window
                ):
                    phrase_proper_bonus[key] += 1

        scored: list[
            tuple[float, int, str]
        ] = []

        # Single concepts need recurrence unless they look like
        # a proper-name entity.
        for key, count in frequency.items():
            proper = proper_bonus.get(key, 0)

            if count < 2 and proper < 1:
                continue

            score = float(count)

            score += min(
                proper,
                4,
            ) * 1.35

            scored.append(
                (
                    score,
                    1,
                    display[key],
                )
            )

        # Phrases are strongly preferred.
        for key, count in phrase_frequency.items():
            proper = phrase_proper_bonus.get(
                key,
                0,
            )

            if count < 2 and proper < 1:
                continue

            word_count = len(key.split())

            score = (
                float(count) * 2.2
                + min(proper, 4) * 1.5
                + word_count * 0.8
            )

            scored.append(
                (
                    score,
                    word_count,
                    phrase_display[key],
                )
            )

        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2].lower(),
            )
        )

        concepts: list[str] = []
        seen: set[str] = set()

        for _, _, value in scored:
            normalized = value.lower()

            if normalized in seen:
                continue

            # Avoid adding a weak single word when a selected phrase
            # already expresses the same entity more precisely.
            if " " not in value:
                if any(
                    re.search(
                        r"\b"
                        + re.escape(normalized)
                        + r"\b",
                        existing.lower(),
                    )
                    for existing in concepts
                    if " " in existing
                ):
                    continue

            seen.add(normalized)
            concepts.append(value)

            if len(concepts) >= 36:
                break

        return concepts

    @staticmethod
    def _slug(value: str) -> str:
        value = value.lower()
        value = re.sub(
            r"[^a-z0-9а-яё]+",
            "_",
            value,
            flags=re.IGNORECASE,
        )
        return value.strip("_") or "project_concept"

    def _build_event_labels(
        self,
        *,
        concepts: list[str],
        title: str,
    ) -> dict[str, tuple[str, ...]]:
        labels: dict[str, tuple[str, ...]] = {}

        # Several strong concepts become independent zero-shot classes.
        # They come from the current script rather than source-code constants.
        for concept in concepts[:18]:
            label = self._slug(concept)

            if label in labels:
                continue

            labels[label] = (
                f"documentary image or footage showing {concept}",
                f"historical or factual visual material related to {concept}",
                f"a scene visually representing {concept} in {title}",
            )

        labels["project_context"] = (
            f"visual material directly related to the documentary {title}",
            "historical archaeological scientific archival or contextual "
            f"material connected with {title}",
            "a documentary scene matching the subject and narrative "
            f"of {title}",
        )

        labels["generic_context"] = (
            "general historical or geographical documentary context",
            "architecture landscape artifact manuscript archive or museum "
            "material useful as documentary context",
        )

        labels["unrelated_private_content"] = (
            "a private selfie or family photograph unrelated to the documentary",
            "an unrelated household object pet food car or personal scene",
            "private everyday material with no connection to the documentary",
        )

        return labels

    def _build_topic_labels(
        self,
        *,
        concepts: list[str],
        title: str,
    ) -> dict[str, tuple[str, ...]]:
        """
        Build project relevance from canonical narrative semantics.

        The canonical narrative_goal is the semantic source of truth.

        Project-level relevance is represented by multiple short prompts
        instead of one oversized prompt. This is important for CLIP-style
        text encoders with bounded context length.

        Production/editorial directives are not semantic evidence.
        visual_strategy, required_assets and emotional_goal are therefore
        deliberately excluded here.

        No project-specific vocabulary is hardcoded.
        """

        root = Path(self.root_dir).resolve()

        db_candidates = (
            root
            / "workspace"
            / "atlas_zero_enterprise.sqlite3",

            root
            / "atlas_zero_enterprise.sqlite3",
        )

        db_path = next(
            (
                candidate
                for candidate in db_candidates
                if candidate.is_file()
            ),
            None,
        )

        narrative_goals: list[str] = []

        if db_path is not None:
            try:
                conn = sqlite3.connect(
                    str(db_path)
                )

                try:
                    rows = conn.execute(
                        """
                        SELECT narrative_goal
                        FROM story_scenes
                        WHERE project_id=?
                        ORDER BY idx
                        """,
                        (self.project_id,),
                    ).fetchall()

                finally:
                    conn.close()

                narrative_goals = [
                    str(row[0] or "").strip()
                    for row in rows
                    if str(row[0] or "").strip()
                ]

            except Exception:
                narrative_goals = []

        # --------------------------------------------------------------
        # Generic production-marker cleanup.
        #
        # These are structural/editorial markers, not film vocabulary.
        # --------------------------------------------------------------

        def clean_narrative(value: str) -> str:
            text = str(value or "")

            text = re.sub(
                r"\bБЛОК\s+\d+\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bBLOCK\s+\d+\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bOPENING\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bSHOCK\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bHOOK\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bФИНАЛ\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\bFINAL\b",
                " ",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"\s+",
                " ",
                text,
            ).strip()

            return text

        cleaned_goals = [
            clean_narrative(goal)
            for goal in narrative_goals
        ]

        cleaned_goals = [
            goal
            for goal in cleaned_goals
            if goal
        ]

        # --------------------------------------------------------------
        # Generate compact scene-level semantic prompts.
        #
        # _extract_concepts already contains the OS-level language/noise
        # filtering logic. Running it per scene prevents late-film themes
        # from disappearing behind globally frequent early-film terms.
        # --------------------------------------------------------------

        relevant_prompts: list[str] = [
            (
                "visual material directly connected to the "
                f"documentary {title}"
            ),
        ]

        seen: set[str] = {
            relevant_prompts[0].lower()
        }

        for goal in cleaned_goals:

            local_concepts: list[str] = []

            try:
                extracted = self._extract_concepts(
                    goal
                )
            except Exception:
                extracted = ()

            for value in extracted or ():
                item = str(value or "").strip()

                if not item:
                    continue

                low = item.lower()

                if low in {
                    existing.lower()
                    for existing
                    in local_concepts
                }:
                    continue

                local_concepts.append(item)

            # Keep every CLIP prompt deliberately short.
            if local_concepts:
                concept_text = ", ".join(
                    local_concepts[:8]
                )

                prompt = (
                    "documentary visual evidence showing "
                    + concept_text
                )

                key = prompt.lower()

                if key not in seen:
                    seen.add(key)
                    relevant_prompts.append(
                        prompt
                    )

            # ----------------------------------------------------------
            # Add a short direct narrative fragment as complementary
            # evidence. Limit length so later scenes do not become one
            # oversized CLIP prompt.
            # ----------------------------------------------------------

            sentences = [
                part.strip()
                for part in re.split(
                    r"(?<=[.!?])\s+",
                    goal,
                )
                if part.strip()
            ]

            if sentences:
                direct = sentences[0]

                if len(direct) > 220:
                    direct = direct[:220].rsplit(
                        " ",
                        1,
                    )[0]

                if direct:
                    prompt = (
                        "documentary scene depicting "
                        + direct
                    )

                    key = prompt.lower()

                    if key not in seen:
                        seen.add(key)
                        relevant_prompts.append(
                            prompt
                        )

        # --------------------------------------------------------------
        # Safety fallback for projects without canonical scenes.
        # Still project-independent.
        # --------------------------------------------------------------

        if len(relevant_prompts) == 1:

            compact = [
                str(value or "").strip()
                for value in concepts or ()
                if str(value or "").strip()
            ]

            if compact:
                relevant_prompts.append(
                    "documentary visual evidence showing "
                    + ", ".join(
                        compact[:12]
                    )
                )

        off_topic_prompts = (
            (
                "visual material unrelated to the "
                f"documentary {title}"
            ),
            (
                "private everyday family household "
                "personal lifestyle or unrelated "
                "entertainment media"
            ),
            (
                "an unrelated subject with no factual "
                "geographic scientific historical or "
                "event connection to the current documentary"
            ),
        )

        return {
            "relevant":
                tuple(relevant_prompts),

            "off_topic":
                tuple(off_topic_prompts),
        }

    @staticmethod
    def _derive_location_hint(
        title: str,
        concepts: list[str],
    ) -> str | None:
        # Do not invent a geographical location.
        # Keep the project title as semantic context instead.
        value = title.strip()
        return value or None

    def _fallback_context(
        self,
        *,
        title: str = "Documentary project",
        source: Path | None = None,
    ) -> ProjectSemanticContextRC2:
        return ProjectSemanticContextRC2(
            project_id=self.project_id,
            title=title,
            source_path=(
                str(source)
                if source is not None
                else None
            ),
            event_labels={
                "documentary_context": (
                    "historical scientific cultural or geographical "
                    "documentary material",
                    "a factual documentary image or scene",
                ),
                "unrelated_private_content": (
                    "private everyday media unrelated to the documentary",
                    "an unrelated selfie household object pet food or car",
                ),
            },
            topic_labels={
                "relevant": (
                    "material relevant to the current documentary project",
                    "historical scientific cultural geographical or "
                    "archival documentary material",
                ),
                "off_topic": (
                    "private or unrelated material with no documentary relevance",
                    "an unrelated everyday personal scene",
                ),
            },
            location_hint=None,
            concepts=(),
        )


