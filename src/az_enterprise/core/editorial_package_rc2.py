from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class EditorialPackageRC2:
    """Build a provider-independent documentary writing package."""

    def __init__(
        self,
        *,
        project_id: str,
        title: str,
        language: str = "ru",
        minimum_duration_sec: float = 720.0,
        use_existing_assets_only: bool = True,
        allow_generated_visuals: bool = False,
    ) -> None:
        self.project_id = project_id
        self.title = title
        self.language = language
        self.minimum_duration_sec = float(
            minimum_duration_sec
        )
        self.use_existing_assets_only = bool(
            use_existing_assets_only
        )
        self.allow_generated_visuals = bool(
            allow_generated_visuals
        )

    def build(
        self,
        *,
        story_strategy: dict[str, Any],
        event_discovery: dict[str, Any],
        semantic_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        scenes = list(
            story_strategy.get("scenes", [])
        )
        clusters = list(
            event_discovery.get(
                "event_clusters",
                [],
            )
        )
        excluded = list(
            event_discovery.get(
                "off_topic_assets",
                [],
            )
        )
        review = list(
            event_discovery.get(
                "review_assets",
                [],
            )
        )

        if not scenes:
            raise ValueError(
                "Story strategy contains no scenes"
            )

        if not clusters:
            raise ValueError(
                "Event discovery contains no clusters"
            )

        cluster_by_id = {
            str(cluster["cluster_id"]): cluster
            for cluster in clusters
        }

        scene_packages = []

        for scene in scenes:
            scene_clusters = [
                cluster_by_id[cluster_id]
                for cluster_id in scene.get(
                    "cluster_ids",
                    [],
                )
                if cluster_id in cluster_by_id
            ]

            scene_packages.append({
                "scene_id": scene["scene_id"],
                "act_id": scene["act_id"],
                "order": scene["order"],
                "title_ru": scene["title_ru"],
                "duration_sec":
                    scene["duration_sec"],
                "narrative_goal_ru":
                    scene["narrative_goal_ru"],
                "emotional_goal_ru":
                    scene["emotional_goal_ru"],
                "visual_strategy_ru":
                    scene["visual_strategy_ru"],
                "cluster_ids": list(
                    scene.get(
                        "cluster_ids",
                        [],
                    )
                ),
                "asset_ids": list(
                    scene.get(
                        "asset_ids",
                        [],
                    )
                ),
                "available_assets": len(
                    scene.get(
                        "asset_ids",
                        [],
                    )
                ),
                "semantic_context": [
                    {
                        "event_type":
                            cluster["event_type"],
                        "time_period":
                            cluster["time_period"],
                        "confidence":
                            cluster["confidence"],
                        "story_value":
                            cluster["story_value"],
                        "description_ru":
                            cluster.get(
                                "description_ru",
                                "",
                            ),
                    }
                    for cluster in scene_clusters
                ],
            })

        strategy = story_strategy.get(
            "strategy",
            {}
        )

        package = {
            "schema_version": "2.7",
            "package_type":
                "documentary_editorial_package",
            "project": {
                "project_id": self.project_id,
                "title": self.title,
                "language": self.language,
                "film_type": strategy.get(
                    "film_type",
                    "documentary",
                ),
                "narrative_strategy":
                    strategy.get(
                        "narrative_strategy",
                        "event_progression",
                    ),
                "target_duration_sec":
                    strategy.get(
                        "target_duration_sec",
                        self.minimum_duration_sec,
                    ),
                "target_audience":
                    strategy.get(
                        "target_audience",
                        "18-55",
                    ),
            },
            "production_constraints": {
                "use_existing_assets_only":
                    self.use_existing_assets_only,
                "allow_generated_visuals":
                    self.allow_generated_visuals,
                "minimum_duration_sec":
                    self.minimum_duration_sec,
                "exclude_off_topic_assets": True,
                "review_assets_policy":
                    "use_only_when_semantically_justified",
            },
            "source_summary": {
                "semantic_assets_total":
                    semantic_analysis.get(
                        "assets_analyzed",
                        len(
                            semantic_analysis.get(
                                "results",
                                [],
                            )
                        ),
                    ),
                "clusters_total": len(clusters),
                "included_assets_total":
                    event_discovery.get(
                        "included_assets_total",
                        0,
                    ),
                "excluded_assets_total":
                    len(excluded),
                "review_assets_total":
                    len(review),
            },
            "acts": story_strategy.get(
                "acts",
                [],
            ),
            "scenes": scene_packages,
            "transitions":
                story_strategy.get(
                    "transitions",
                    [],
                ),
            "event_clusters": clusters,
            "excluded_assets": excluded,
            "review_assets": review,
            "writing_assignment": {
                "deliverable":
                    "Полный документальный сценарий и текст диктора",
                "language": "Русский",
                "minimum_duration_minutes": 12,
                "target_words": 3300,
                "style": (
                    "Современный документальный фильм: "
                    "фактический, живой, атмосферный, "
                    "без канцелярита и шаблонных повторов."
                ),
                "requirements": [
                    "Сформулировать единую авторскую идею фильма.",
                    "Создать сильное вступление с удержанием внимания.",
                    "Различать повторяющиеся сцены одного типа.",
                    "Не повторять одинаковые факты и формулировки.",
                    "Связать сцены естественными переходами.",
                    "Использовать только подтверждённые события.",
                    "Не придумывать интервью, персонажей и съёмки.",
                    "Оставлять место для естественного звука праздника.",
                    "Завершить фильм эмоциональным, но точным финалом.",
                ],
                "forbidden": [
                    "Придумывать отсутствующие визуальные материалы.",
                    "Включать исключённые посторонние файлы.",
                    "Описывать техническую работу монтажной системы.",
                    "Заполнять длительность повторяющимися фразами.",
                    "Выдавать предположения за подтверждённые факты.",
                ],
                "required_output_structure": {
                    "film_concept": "Одна центральная идея фильма.",
                    "scene_scripts": (
                        "Отдельный текст диктора для каждой сцены "
                        "SC01–SC19."
                    ),
                    "full_voiceover": (
                        "Единый полный текст диктора без технических "
                        "комментариев."
                    ),
                    "scene_word_counts": (
                        "Количество слов и расчётная длительность "
                        "каждой сцены."
                    ),
                },
            },
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        self.validate(package)
        return package

    @staticmethod
    def validate(
        package: dict[str, Any],
    ) -> None:
        if not package["project"]["project_id"]:
            raise ValueError(
                "project_id is required"
            )

        if not package["scenes"]:
            raise ValueError(
                "Editorial package requires scenes"
            )

        if not package["event_clusters"]:
            raise ValueError(
                "Editorial package requires clusters"
            )

        scene_ids = [
            scene["scene_id"]
            for scene in package["scenes"]
        ]

        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError(
                "Duplicate scene IDs"
            )

        if (
            package["production_constraints"]
            ["use_existing_assets_only"]
            and package[
                "production_constraints"
            ]["allow_generated_visuals"]
        ):
            raise ValueError(
                "Existing-assets-only mode cannot "
                "allow generated visuals"
            )
