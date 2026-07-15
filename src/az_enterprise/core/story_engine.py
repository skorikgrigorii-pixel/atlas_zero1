from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .database import Database
from .events import EventBus


@dataclass(frozen=True)
class SceneBlueprint:
    scene_id: str
    block: str
    title: str
    duration_sec: float
    narrative_goal: str
    emotional_goal: str
    visual_strategy: str
    visual_needs: tuple[str, ...]
    preferred_motion: tuple[str, ...]


SCENE_BLUEPRINTS: list[SceneBlueprint] = [
    SceneBlueprint('S01','B01','Холодный факт исчезновения',52,'Открыть фильм не справкой, а последствиями катастрофы.','тревога','минималистичные крупные детали, затем переход к масштабу Арктики',('ice detail','artifact close','note close','arctic wide'),('slow push-in','macro drift','fade from black')),
    SceneBlueprint('S02','B01','Экспедиция входит в Арктику',78,'Показать два корабля как героев фильма и изоляцию в ледовом пространстве.','изоляция', 'общие планы кораблей, ледяные проходы, холодный туман',('ship ice wide','ship ice video','drone arctic','hull ice'),('slow drone','dolly forward','slow pan')),
    SceneBlueprint('S03','B01','Люди на кораблях',70,'Перевести масштаб экспедиции к людям, команде и командованию.','человеческое присутствие', 'палуба, экипаж, такелаж, офицеры',('crew captain deck','crew working','rigging ice','deck detail'),('slow track','handheld subtle','push-in')),
    SceneBlueprint('S04','B02','Первые годы молчания',62,'Показать, что тревога возникла поздно и время было потеряно.','запоздалое осознание', 'архивы Адмиралтейства, карты, поисковые корабли',('archive document','map search','ship ice wide','journal close'),('paper reveal','map pan','dissolve')),
    SceneBlueprint('S05','B02','Джейн Франклин и поиски',62,'Показать личную настойчивость как двигатель расследования.','решимость', 'письма, портретный силуэт, карты маршрутов',('archive portrait','letter document','map routes','search ship'),('slow push-in','map trace','dissolve')),
    SceneBlueprint('S06','B02','Остров Бичи',82,'Остров Бичи меняет понимание: катастрофа ещё не началась, но первые смерти уже есть.','спокойное потрясение', 'лагерь, могилы, банки, камни, пустота',('ice camp grave','grave marker','can archive','arctic coast'),('slow pullback','static hold','cold dissolve')),
    SceneBlueprint('S07','B03','Находка записки',78,'Подвести к главному письменному документу экспедиции.','прикосновение к событию', 'камни, металлический цилиндр, бумага, рука поисковика',('document note close','stone cairn','metal cylinder','paper reveal'),('macro push','paper unfold','hold')),
    SceneBlueprint('S08','B03','Две записи на одном листе',84,'Показать смену смысла: от благополучной записи к сообщению о смерти и уходе.','резкая смена ожиданий', 'исторический бланк, даты, поля документа, карта ухода',('document note map','document text','map route','ship trapped'),('slow scan','date reveal','map move')),
    SceneBlueprint('S09','B03','Сто пять человек уходят пешком',70,'Показать организованный уход и начало молчания.','неизвестность', 'цепочка людей, следы в снегу, белая пустота',('people snow trail','footprints snow','white horizon','sled silhouette'),('slow fade','long lens','snow drift')),
    SceneBlueprint('S10','B04','Шлюпка на санях',74,'Начать блок материальными следами, которые не складываются в логику выживания.','недоумение', 'лодка на санях, каменистый берег, внутреннее пространство лодки',('boat sled ice','arctic coast','wood runners','boat interior'),('slow reveal','side track','static hold')),
    SceneBlueprint('S11','B04','Странный груз',70,'Показать, что люди тащили вещи, не увеличивавшие шансы спасения.','нарастающее непонимание', 'серебро, книги, патроны, предметы быта',('silver spoon','object close','book archive','rifle detail'),('macro slide','tabletop pan','hard cut')),
    SceneBlueprint('S12','B04','Кости и спорные улики',78,'Ввести признаки обработки костей через факты, без сенсационности.','шок без акцента', 'археология, кости, архивные фотографии, лабораторный стол',('bones archive lab','bone close','lab table','archive folder'),('static macro','slow tilt','folder close')),
    SceneBlueprint('S13','B05','Наука возвращается на Бичи',82,'Показать переход расследования из Арктики в лабораторию.','сосредоточенность', 'экспедиция 1984, мерзлота, гроб, лица исследователей',('lab archive','beechy camp','forensic dig','wood coffin'),('documentary handheld','slow reveal','cutaway')),
    SceneBlueprint('S14','B05','Торрингтон и масштаб исследования',70,'Показать уникальную сохранность тел этично и без натурализма.','удивление', 'архивные фото, одежда, медицинские записи, руки исследователей',('archive portrait','medical notes','clothing detail','lab hands'),('slow push','macro detail','dissolve')),
    SceneBlueprint('S15','B05','Свинец и новая картина',78,'Показать, как гипотеза стала популярной и как последующие данные усложнили ответ.','ответ снова сложнее', 'консервы, припой, лаборатория, газетные публикации',('lead can archive','lab analysis','newspaper archive','medical record'),('macro metal','paper montage','lab pan')),
    SceneBlueprint('S16','B06','Современные поиски',78,'Показать возвращение поисков с технологиями и ролью свидетельств инуитов.','осторожная надежда', 'исследовательское судно, спутники, гидролокатор, карты',('sonar screen','research vessel','satellite map','underwater robot'),('screen scan','drone coast','map overlay')),
    SceneBlueprint('S17','B06','Erebus и Terror найдены',86,'Показать находку кораблей как начало нового этапа, а не конец расследования.','открытие и удивление', 'подводные кадры, корпус, люки, интерьер, карты положения',('underwater ship','shipwreck hull','closed hatch','interior cabin'),('rov glide','slow track','dark dissolve')),
    SceneBlueprint('S18','B06','Финал: история сохраняет следы',80,'Спокойно завершить фильм: ответы есть, но последнее молчание остаётся.','уважение', 'монтаж ключевых мест, Арктика сверху, логотип',('ice wide finale','empty horizon','ship memory','atlas logo'),('slow pullback','fade out','snow increase')),
]


class StoryEngine:
    """Alpha 2.3 Story Engine.

    Builds a real scene structure and a shot plan instead of a flat synthetic list.
    The engine uses the locked Franklin narrative blueprint, distributes shot timing
    across scenes, rotates visual needs and camera motion, and writes scenes + shots
    to SQLite so Director AI and Timeline can operate on a structured film model.
    """

    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS story_scenes(
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          idx INTEGER NOT NULL,
          block TEXT NOT NULL,
          title TEXT NOT NULL,
          start_sec REAL NOT NULL,
          end_sec REAL NOT NULL,
          duration_sec REAL NOT NULL,
          target_shots INTEGER NOT NULL,
          narrative_goal TEXT,
          emotional_goal TEXT,
          visual_strategy TEXT,
          required_assets TEXT,
          status TEXT DEFAULT 'planned',
          coverage REAL DEFAULT 0,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        self.db.conn.commit()

    def build_shots(self, target_count: int = 165, duration_sec: float = 960.0) -> dict[str, Any]:
        self.db.execute('DELETE FROM shots WHERE project_id=?', (self.project_id,))
        self.db.execute('DELETE FROM story_scenes WHERE project_id=?', (self.project_id,))
        scene_counts = self._allocate_shots(target_count)
        current_time = 0.0
        shot_idx = 1
        scene_rows: list[tuple[Any, ...]] = []
        shot_rows: list[tuple[Any, ...]] = []
        for scene_idx, bp in enumerate(SCENE_BLUEPRINTS, start=1):
            count = scene_counts[scene_idx - 1]
            scene_duration = round(duration_sec * (bp.duration_sec / self._blueprint_duration()), 3)
            start = round(current_time, 3)
            end = round(current_time + scene_duration, 3)
            scene_rows.append((
                bp.scene_id, self.project_id, scene_idx, bp.block, bp.title, start, end, scene_duration, count,
                bp.narrative_goal, bp.emotional_goal, bp.visual_strategy, json.dumps(list(bp.visual_needs), ensure_ascii=False), 'planned', 0.0
            ))
            shot_len = scene_duration / max(count, 1)
            for local_idx in range(count):
                s_start = round(start + local_idx * shot_len, 3)
                s_end = round(start + (local_idx + 1) * shot_len, 3)
                visual_need = bp.visual_needs[local_idx % len(bp.visual_needs)]
                motion = bp.preferred_motion[local_idx % len(bp.preferred_motion)]
                transition = self._transition_for(scene_idx, local_idx, count)
                story_goal = f'{bp.title}. {bp.narrative_goal}'
                shot_rows.append((
                    f'shot_{shot_idx:04d}', self.project_id, shot_idx, s_start, s_end, bp.block, story_goal,
                    visual_need, bp.emotional_goal, 'missing', None, transition, motion
                ))
                shot_idx += 1
            current_time = end
        self.db.many('''
            INSERT INTO story_scenes(id,project_id,idx,block,title,start_sec,end_sec,duration_sec,target_shots,narrative_goal,emotional_goal,visual_strategy,required_assets,status,coverage)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', scene_rows)
        self.db.many('''
            INSERT INTO shots(id,project_id,idx,start_sec,end_sec,block,story_goal,visual_need,emotion,status,assigned_asset_id,transition,camera_motion)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', shot_rows)
        self.bus.emit('STORY_SCENES_BUILT', {'scenes': len(scene_rows), 'shots': len(shot_rows), 'duration_sec': duration_sec})
        return {'version': '2.3', 'scenes': len(scene_rows), 'shots': len(shot_rows), 'duration_sec': duration_sec}

    def build_from_strategy(
        self,
        strategy_payload: dict[str, Any],
        *,
        target_count: int | None = None,
    ) -> dict[str, Any]:
        """Build story scenes and shots from RC2.6 strategy output.

        Franklin remains supported through build_shots(), while semantic
        projects may supply dynamically created scenes.
        """
        scenes = list(
            strategy_payload.get("scenes", [])
        )

        if not scenes:
            raise ValueError(
                "Strategy payload contains no scenes"
            )

        target_duration = float(
            strategy_payload.get(
                "strategy",
                {},
            ).get(
                "target_duration_sec",
                0.0,
            )
        )

        if target_duration <= 0:
            target_duration = sum(
                float(
                    scene.get(
                        "duration_sec",
                        0.0,
                    )
                )
                for scene in scenes
            )

        if target_duration <= 0:
            raise ValueError(
                "Strategy target duration must be > 0"
            )

        if target_count is None:
            target_count = max(
                len(scenes) * 4,
                round(target_duration / 8.0),
            )

        target_count = max(
            int(target_count),
            len(scenes),
        )

        weights = [
            max(
                float(
                    scene.get(
                        "duration_sec",
                        0.0,
                    )
                ),
                1.0,
            )
            for scene in scenes
        ]

        counts = [1] * len(scenes)
        remaining = target_count - len(scenes)

        for _ in range(remaining):
            index = max(
                range(len(scenes)),
                key=lambda i: (
                    weights[i] / (counts[i] + 1),
                    -i,
                ),
            )
            counts[index] += 1

        self.db.execute(
            "DELETE FROM shots WHERE project_id=?",
            (self.project_id,),
        )
        self.db.execute(
            "DELETE FROM story_scenes WHERE project_id=?",
            (self.project_id,),
        )

        current_time = 0.0
        shot_index = 1
        scene_rows: list[tuple[Any, ...]] = []
        shot_rows: list[tuple[Any, ...]] = []

        for scene_index, scene in enumerate(
            scenes,
            start=1,
        ):
            duration = float(
                scene["duration_sec"]
            )
            start = round(current_time, 3)
            end = round(
                current_time + duration,
                3,
            )

            scene_id = str(
                scene.get("scene_id")
                or f"SC{scene_index:02d}"
            )
            act_id = str(
                scene.get("act_id")
                or "ACT00"
            )
            title = str(
                scene.get("title_ru")
                or f"Сцена {scene_index}"
            )
            narrative_goal = str(
                scene.get("narrative_goal_ru")
                or ""
            )
            emotional_goal = str(
                scene.get("emotional_goal_ru")
                or "neutral"
            )
            visual_strategy = str(
                scene.get("visual_strategy_ru")
                or ""
            )
            cluster_ids = list(
                scene.get("cluster_ids")
                or []
            )
            asset_ids = [
                str(asset_id)
                for asset_id
                in (
                    scene.get("asset_ids")
                    or []
                )
            ]

            required_assets = {
                "cluster_ids": cluster_ids,
                "asset_ids": asset_ids,
                "use_existing_assets_only": bool(
                    strategy_payload.get(
                        "strategy",
                        {},
                    ).get(
                        "use_existing_assets_only",
                        False,
                    )
                ),
            }

            count = counts[scene_index - 1]

            scene_rows.append((
                scene_id,
                self.project_id,
                scene_index,
                act_id,
                title,
                start,
                end,
                duration,
                count,
                narrative_goal,
                emotional_goal,
                visual_strategy,
                json.dumps(
                    required_assets,
                    ensure_ascii=False,
                ),
                "planned",
                0.0,
            ))

            shot_duration = duration / count

            for local_index in range(count):
                shot_start = round(
                    start
                    + local_index
                    * shot_duration,
                    3,
                )
                shot_end = round(
                    start
                    + (local_index + 1)
                    * shot_duration,
                    3,
                )

                assigned_asset_id = (
                    asset_ids[
                        local_index
                        % len(asset_ids)
                    ]
                    if asset_ids
                    else None
                )

                status = (
                    "assigned"
                    if assigned_asset_id
                    else "missing"
                )

                visual_need = (
                    cluster_ids[
                        local_index
                        % len(cluster_ids)
                    ]
                    if cluster_ids
                    else title
                )

                transition = self._transition_for(
                    scene_index,
                    local_index,
                    count,
                )

                camera_motion = (
                    "slow pan"
                    if local_index % 3 == 0
                    else (
                        "slow push-in"
                        if local_index % 3 == 1
                        else "static hold"
                    )
                )

                story_goal = (
                    f"{title}. {narrative_goal}"
                )

                shot_rows.append((
                    f"shot_{shot_index:04d}",
                    self.project_id,
                    shot_index,
                    shot_start,
                    shot_end,
                    act_id,
                    story_goal,
                    visual_need,
                    emotional_goal,
                    status,
                    assigned_asset_id,
                    transition,
                    camera_motion,
                ))

                shot_index += 1

            current_time = end

        self.db.many(
            """
            INSERT INTO story_scenes(
                id,
                project_id,
                idx,
                block,
                title,
                start_sec,
                end_sec,
                duration_sec,
                target_shots,
                narrative_goal,
                emotional_goal,
                visual_strategy,
                required_assets,
                status,
                coverage
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            scene_rows,
        )

        self.db.many(
            """
            INSERT INTO shots(
                id,
                project_id,
                idx,
                start_sec,
                end_sec,
                block,
                story_goal,
                visual_need,
                emotion,
                status,
                assigned_asset_id,
                transition,
                camera_motion
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            shot_rows,
        )

        self.bus.emit(
            "STORY_SCENES_BUILT_FROM_STRATEGY",
            {
                "scenes": len(scene_rows),
                "shots": len(shot_rows),
                "duration_sec": round(
                    current_time,
                    3,
                ),
            },
        )

        return {
            "version": "2.6",
            "mode": "semantic_strategy",
            "project_id": self.project_id,
            "scenes": len(scene_rows),
            "shots": len(shot_rows),
            "duration_sec": round(
                current_time,
                3,
            ),
            "assigned_shots": sum(
                1
                for row in shot_rows
                if row[10]
            ),
            "missing_shots": sum(
                1
                for row in shot_rows
                if not row[10]
            ),
        }

    def _blueprint_duration(self) -> float:
        return sum(bp.duration_sec for bp in SCENE_BLUEPRINTS)

    def _allocate_shots(self, target_count: int) -> list[int]:
        target_count = max(0, int(target_count))
        raw = [0] * len(SCENE_BLUEPRINTS)
        if target_count <= 0:
            return raw

        for i in range(min(target_count, len(raw))):
            raw[i] = 1

        remaining = target_count - sum(raw)
        if remaining <= 0:
            return raw

        weights = [bp.duration_sec for bp in SCENE_BLUEPRINTS]
        for _ in range(remaining):
            idx = max(range(len(raw)), key=lambda i: (weights[i] / (raw[i] + 1), i))
            raw[idx] += 1
        return raw

    def _transition_for(self, scene_idx: int, local_idx: int, count: int) -> str:
        if scene_idx == 1 and local_idx == 0:
            return 'fade from black'
        if local_idx == 0:
            return 'dissolve'
        if local_idx == count - 1:
            return 'soft dissolve'
        return 'cut'
