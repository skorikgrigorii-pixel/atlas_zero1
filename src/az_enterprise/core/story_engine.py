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
    SceneBlueprint('S01','B01','РҐРѕР»РѕРґРЅС‹Р№ С„Р°РєС‚ РёСЃС‡РµР·РЅРѕРІРµРЅРёСЏ',52,'РћС‚РєСЂС‹С‚СЊ С„РёР»СЊРј РЅРµ СЃРїСЂР°РІРєРѕР№, Р° РїРѕСЃР»РµРґСЃС‚РІРёСЏРјРё РєР°С‚Р°СЃС‚СЂРѕС„С‹.','С‚СЂРµРІРѕРіР°','РјРёРЅРёРјР°Р»РёСЃС‚РёС‡РЅС‹Рµ РєСЂСѓРїРЅС‹Рµ РґРµС‚Р°Р»Рё, Р·Р°С‚РµРј РїРµСЂРµС…РѕРґ Рє РјР°СЃС€С‚Р°Р±Сѓ РђСЂРєС‚РёРєРё',('ice detail','artifact close','note close','arctic wide'),('slow push-in','macro drift','fade from black')),
    SceneBlueprint('S02','B01','Р­РєСЃРїРµРґРёС†РёСЏ РІС…РѕРґРёС‚ РІ РђСЂРєС‚РёРєСѓ',78,'РџРѕРєР°Р·Р°С‚СЊ РґРІР° РєРѕСЂР°Р±Р»СЏ РєР°Рє РіРµСЂРѕРµРІ С„РёР»СЊРјР° Рё РёР·РѕР»СЏС†РёСЋ РІ Р»РµРґРѕРІРѕРј РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРµ.','РёР·РѕР»СЏС†РёСЏ', 'РѕР±С‰РёРµ РїР»Р°РЅС‹ РєРѕСЂР°Р±Р»РµР№, Р»РµРґСЏРЅС‹Рµ РїСЂРѕС…РѕРґС‹, С…РѕР»РѕРґРЅС‹Р№ С‚СѓРјР°РЅ',('ship ice wide','ship ice video','drone arctic','hull ice'),('slow drone','dolly forward','slow pan')),
    SceneBlueprint('S03','B01','Р›СЋРґРё РЅР° РєРѕСЂР°Р±Р»СЏС…',70,'РџРµСЂРµРІРµСЃС‚Рё РјР°СЃС€С‚Р°Р± СЌРєСЃРїРµРґРёС†РёРё Рє Р»СЋРґСЏРј, РєРѕРјР°РЅРґРµ Рё РєРѕРјР°РЅРґРѕРІР°РЅРёСЋ.','С‡РµР»РѕРІРµС‡РµСЃРєРѕРµ РїСЂРёСЃСѓС‚СЃС‚РІРёРµ', 'РїР°Р»СѓР±Р°, СЌРєРёРїР°Р¶, С‚Р°РєРµР»Р°Р¶, РѕС„РёС†РµСЂС‹',('crew captain deck','crew working','rigging ice','deck detail'),('slow track','handheld subtle','push-in')),
    SceneBlueprint('S04','B02','РџРµСЂРІС‹Рµ РіРѕРґС‹ РјРѕР»С‡Р°РЅРёСЏ',62,'РџРѕРєР°Р·Р°С‚СЊ, С‡С‚Рѕ С‚СЂРµРІРѕРіР° РІРѕР·РЅРёРєР»Р° РїРѕР·РґРЅРѕ Рё РІСЂРµРјСЏ Р±С‹Р»Рѕ РїРѕС‚РµСЂСЏРЅРѕ.','Р·Р°РїРѕР·РґР°Р»РѕРµ РѕСЃРѕР·РЅР°РЅРёРµ', 'Р°СЂС…РёРІС‹ РђРґРјРёСЂР°Р»С‚РµР№СЃС‚РІР°, РєР°СЂС‚С‹, РїРѕРёСЃРєРѕРІС‹Рµ РєРѕСЂР°Р±Р»Рё',('archive document','map search','ship ice wide','journal close'),('paper reveal','map pan','dissolve')),
    SceneBlueprint('S05','B02','Р”Р¶РµР№РЅ Р¤СЂР°РЅРєР»РёРЅ Рё РїРѕРёСЃРєРё',62,'РџРѕРєР°Р·Р°С‚СЊ Р»РёС‡РЅСѓСЋ РЅР°СЃС‚РѕР№С‡РёРІРѕСЃС‚СЊ РєР°Рє РґРІРёРіР°С‚РµР»СЊ СЂР°СЃСЃР»РµРґРѕРІР°РЅРёСЏ.','СЂРµС€РёРјРѕСЃС‚СЊ', 'РїРёСЃСЊРјР°, РїРѕСЂС‚СЂРµС‚РЅС‹Р№ СЃРёР»СѓСЌС‚, РєР°СЂС‚С‹ РјР°СЂС€СЂСѓС‚РѕРІ',('archive portrait','letter document','map routes','search ship'),('slow push-in','map trace','dissolve')),
    SceneBlueprint('S06','B02','РћСЃС‚СЂРѕРІ Р‘РёС‡Рё',82,'РћСЃС‚СЂРѕРІ Р‘РёС‡Рё РјРµРЅСЏРµС‚ РїРѕРЅРёРјР°РЅРёРµ: РєР°С‚Р°СЃС‚СЂРѕС„Р° РµС‰С‘ РЅРµ РЅР°С‡Р°Р»Р°СЃСЊ, РЅРѕ РїРµСЂРІС‹Рµ СЃРјРµСЂС‚Рё СѓР¶Рµ РµСЃС‚СЊ.','СЃРїРѕРєРѕР№РЅРѕРµ РїРѕС‚СЂСЏСЃРµРЅРёРµ', 'Р»Р°РіРµСЂСЊ, РјРѕРіРёР»С‹, Р±Р°РЅРєРё, РєР°РјРЅРё, РїСѓСЃС‚РѕС‚Р°',('ice camp grave','grave marker','can archive','arctic coast'),('slow pullback','static hold','cold dissolve')),
    SceneBlueprint('S07','B03','РќР°С…РѕРґРєР° Р·Р°РїРёСЃРєРё',78,'РџРѕРґРІРµСЃС‚Рё Рє РіР»Р°РІРЅРѕРјСѓ РїРёСЃСЊРјРµРЅРЅРѕРјСѓ РґРѕРєСѓРјРµРЅС‚Сѓ СЌРєСЃРїРµРґРёС†РёРё.','РїСЂРёРєРѕСЃРЅРѕРІРµРЅРёРµ Рє СЃРѕР±С‹С‚РёСЋ', 'РєР°РјРЅРё, РјРµС‚Р°Р»Р»РёС‡РµСЃРєРёР№ С†РёР»РёРЅРґСЂ, Р±СѓРјР°РіР°, СЂСѓРєР° РїРѕРёСЃРєРѕРІРёРєР°',('document note close','stone cairn','metal cylinder','paper reveal'),('macro push','paper unfold','hold')),
    SceneBlueprint('S08','B03','Р”РІРµ Р·Р°РїРёСЃРё РЅР° РѕРґРЅРѕРј Р»РёСЃС‚Рµ',84,'РџРѕРєР°Р·Р°С‚СЊ СЃРјРµРЅСѓ СЃРјС‹СЃР»Р°: РѕС‚ Р±Р»Р°РіРѕРїРѕР»СѓС‡РЅРѕР№ Р·Р°РїРёСЃРё Рє СЃРѕРѕР±С‰РµРЅРёСЋ Рѕ СЃРјРµСЂС‚Рё Рё СѓС…РѕРґРµ.','СЂРµР·РєР°СЏ СЃРјРµРЅР° РѕР¶РёРґР°РЅРёР№', 'РёСЃС‚РѕСЂРёС‡РµСЃРєРёР№ Р±Р»Р°РЅРє, РґР°С‚С‹, РїРѕР»СЏ РґРѕРєСѓРјРµРЅС‚Р°, РєР°СЂС‚Р° СѓС…РѕРґР°',('document note map','document text','map route','ship trapped'),('slow scan','date reveal','map move')),
    SceneBlueprint('S09','B03','РЎС‚Рѕ РїСЏС‚СЊ С‡РµР»РѕРІРµРє СѓС…РѕРґСЏС‚ РїРµС€РєРѕРј',70,'РџРѕРєР°Р·Р°С‚СЊ РѕСЂРіР°РЅРёР·РѕРІР°РЅРЅС‹Р№ СѓС…РѕРґ Рё РЅР°С‡Р°Р»Рѕ РјРѕР»С‡Р°РЅРёСЏ.','РЅРµРёР·РІРµСЃС‚РЅРѕСЃС‚СЊ', 'С†РµРїРѕС‡РєР° Р»СЋРґРµР№, СЃР»РµРґС‹ РІ СЃРЅРµРіСѓ, Р±РµР»Р°СЏ РїСѓСЃС‚РѕС‚Р°',('people snow trail','footprints snow','white horizon','sled silhouette'),('slow fade','long lens','snow drift')),
    SceneBlueprint('S10','B04','РЁР»СЋРїРєР° РЅР° СЃР°РЅСЏС…',74,'РќР°С‡Р°С‚СЊ Р±Р»РѕРє РјР°С‚РµСЂРёР°Р»СЊРЅС‹РјРё СЃР»РµРґР°РјРё, РєРѕС‚РѕСЂС‹Рµ РЅРµ СЃРєР»Р°РґС‹РІР°СЋС‚СЃСЏ РІ Р»РѕРіРёРєСѓ РІС‹Р¶РёРІР°РЅРёСЏ.','РЅРµРґРѕСѓРјРµРЅРёРµ', 'Р»РѕРґРєР° РЅР° СЃР°РЅСЏС…, РєР°РјРµРЅРёСЃС‚С‹Р№ Р±РµСЂРµРі, РІРЅСѓС‚СЂРµРЅРЅРµРµ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ Р»РѕРґРєРё',('boat sled ice','arctic coast','wood runners','boat interior'),('slow reveal','side track','static hold')),
    SceneBlueprint('S11','B04','РЎС‚СЂР°РЅРЅС‹Р№ РіСЂСѓР·',70,'РџРѕРєР°Р·Р°С‚СЊ, С‡С‚Рѕ Р»СЋРґРё С‚Р°С‰РёР»Рё РІРµС‰Рё, РЅРµ СѓРІРµР»РёС‡РёРІР°РІС€РёРµ С€Р°РЅСЃС‹ СЃРїР°СЃРµРЅРёСЏ.','РЅР°СЂР°СЃС‚Р°СЋС‰РµРµ РЅРµРїРѕРЅРёРјР°РЅРёРµ', 'СЃРµСЂРµР±СЂРѕ, РєРЅРёРіРё, РїР°С‚СЂРѕРЅС‹, РїСЂРµРґРјРµС‚С‹ Р±С‹С‚Р°',('silver spoon','object close','book archive','rifle detail'),('macro slide','tabletop pan','hard cut')),
    SceneBlueprint('S12','B04','РљРѕСЃС‚Рё Рё СЃРїРѕСЂРЅС‹Рµ СѓР»РёРєРё',78,'Р’РІРµСЃС‚Рё РїСЂРёР·РЅР°РєРё РѕР±СЂР°Р±РѕС‚РєРё РєРѕСЃС‚РµР№ С‡РµСЂРµР· С„Р°РєС‚С‹, Р±РµР· СЃРµРЅСЃР°С†РёРѕРЅРЅРѕСЃС‚Рё.','С€РѕРє Р±РµР· Р°РєС†РµРЅС‚Р°', 'Р°СЂС…РµРѕР»РѕРіРёСЏ, РєРѕСЃС‚Рё, Р°СЂС…РёРІРЅС‹Рµ С„РѕС‚РѕРіСЂР°С„РёРё, Р»Р°Р±РѕСЂР°С‚РѕСЂРЅС‹Р№ СЃС‚РѕР»',('bones archive lab','bone close','lab table','archive folder'),('static macro','slow tilt','folder close')),
    SceneBlueprint('S13','B05','РќР°СѓРєР° РІРѕР·РІСЂР°С‰Р°РµС‚СЃСЏ РЅР° Р‘РёС‡Рё',82,'РџРѕРєР°Р·Р°С‚СЊ РїРµСЂРµС…РѕРґ СЂР°СЃСЃР»РµРґРѕРІР°РЅРёСЏ РёР· РђСЂРєС‚РёРєРё РІ Р»Р°Р±РѕСЂР°С‚РѕСЂРёСЋ.','СЃРѕСЃСЂРµРґРѕС‚РѕС‡РµРЅРЅРѕСЃС‚СЊ', 'СЌРєСЃРїРµРґРёС†РёСЏ 1984, РјРµСЂР·Р»РѕС‚Р°, РіСЂРѕР±, Р»РёС†Р° РёСЃСЃР»РµРґРѕРІР°С‚РµР»РµР№',('lab archive','beechy camp','forensic dig','wood coffin'),('documentary handheld','slow reveal','cutaway')),
    SceneBlueprint('S14','B05','РўРѕСЂСЂРёРЅРіС‚РѕРЅ Рё РјР°СЃС€С‚Р°Р± РёСЃСЃР»РµРґРѕРІР°РЅРёСЏ',70,'РџРѕРєР°Р·Р°С‚СЊ СѓРЅРёРєР°Р»СЊРЅСѓСЋ СЃРѕС…СЂР°РЅРЅРѕСЃС‚СЊ С‚РµР» СЌС‚РёС‡РЅРѕ Рё Р±РµР· РЅР°С‚СѓСЂР°Р»РёР·РјР°.','СѓРґРёРІР»РµРЅРёРµ', 'Р°СЂС…РёРІРЅС‹Рµ С„РѕС‚Рѕ, РѕРґРµР¶РґР°, РјРµРґРёС†РёРЅСЃРєРёРµ Р·Р°РїРёСЃРё, СЂСѓРєРё РёСЃСЃР»РµРґРѕРІР°С‚РµР»РµР№',('archive portrait','medical notes','clothing detail','lab hands'),('slow push','macro detail','dissolve')),
    SceneBlueprint('S15','B05','РЎРІРёРЅРµС† Рё РЅРѕРІР°СЏ РєР°СЂС‚РёРЅР°',78,'РџРѕРєР°Р·Р°С‚СЊ, РєР°Рє РіРёРїРѕС‚РµР·Р° СЃС‚Р°Р»Р° РїРѕРїСѓР»СЏСЂРЅРѕР№ Рё РєР°Рє РїРѕСЃР»РµРґСѓСЋС‰РёРµ РґР°РЅРЅС‹Рµ СѓСЃР»РѕР¶РЅРёР»Рё РѕС‚РІРµС‚.','РѕС‚РІРµС‚ СЃРЅРѕРІР° СЃР»РѕР¶РЅРµРµ', 'РєРѕРЅСЃРµСЂРІС‹, РїСЂРёРїРѕР№, Р»Р°Р±РѕСЂР°С‚РѕСЂРёСЏ, РіР°Р·РµС‚РЅС‹Рµ РїСѓР±Р»РёРєР°С†РёРё',('lead can archive','lab analysis','newspaper archive','medical record'),('macro metal','paper montage','lab pan')),
    SceneBlueprint('S16','B06','РЎРѕРІСЂРµРјРµРЅРЅС‹Рµ РїРѕРёСЃРєРё',78,'РџРѕРєР°Р·Р°С‚СЊ РІРѕР·РІСЂР°С‰РµРЅРёРµ РїРѕРёСЃРєРѕРІ СЃ С‚РµС…РЅРѕР»РѕРіРёСЏРјРё Рё СЂРѕР»СЊСЋ СЃРІРёРґРµС‚РµР»СЊСЃС‚РІ РёРЅСѓРёС‚РѕРІ.','РѕСЃС‚РѕСЂРѕР¶РЅР°СЏ РЅР°РґРµР¶РґР°', 'РёСЃСЃР»РµРґРѕРІР°С‚РµР»СЊСЃРєРѕРµ СЃСѓРґРЅРѕ, СЃРїСѓС‚РЅРёРєРё, РіРёРґСЂРѕР»РѕРєР°С‚РѕСЂ, РєР°СЂС‚С‹',('sonar screen','research vessel','satellite map','underwater robot'),('screen scan','drone coast','map overlay')),
    SceneBlueprint('S17','B06','Erebus Рё Terror РЅР°Р№РґРµРЅС‹',86,'РџРѕРєР°Р·Р°С‚СЊ РЅР°С…РѕРґРєСѓ РєРѕСЂР°Р±Р»РµР№ РєР°Рє РЅР°С‡Р°Р»Рѕ РЅРѕРІРѕРіРѕ СЌС‚Р°РїР°, Р° РЅРµ РєРѕРЅРµС† СЂР°СЃСЃР»РµРґРѕРІР°РЅРёСЏ.','РѕС‚РєСЂС‹С‚РёРµ Рё СѓРґРёРІР»РµРЅРёРµ', 'РїРѕРґРІРѕРґРЅС‹Рµ РєР°РґСЂС‹, РєРѕСЂРїСѓСЃ, Р»СЋРєРё, РёРЅС‚РµСЂСЊРµСЂ, РєР°СЂС‚С‹ РїРѕР»РѕР¶РµРЅРёСЏ',('underwater ship','shipwreck hull','closed hatch','interior cabin'),('rov glide','slow track','dark dissolve')),
    SceneBlueprint('S18','B06','Р¤РёРЅР°Р»: РёСЃС‚РѕСЂРёСЏ СЃРѕС…СЂР°РЅСЏРµС‚ СЃР»РµРґС‹',80,'РЎРїРѕРєРѕР№РЅРѕ Р·Р°РІРµСЂС€РёС‚СЊ С„РёР»СЊРј: РѕС‚РІРµС‚С‹ РµСЃС‚СЊ, РЅРѕ РїРѕСЃР»РµРґРЅРµРµ РјРѕР»С‡Р°РЅРёРµ РѕСЃС‚Р°С‘С‚СЃСЏ.','СѓРІР°Р¶РµРЅРёРµ', 'РјРѕРЅС‚Р°Р¶ РєР»СЋС‡РµРІС‹С… РјРµСЃС‚, РђСЂРєС‚РёРєР° СЃРІРµСЂС…Сѓ, Р»РѕРіРѕС‚РёРї',('ice wide finale','empty horizon','ship memory','atlas logo'),('slow pullback','fade out','snow increase')),
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
                or f"РЎС†РµРЅР° {scene_index}"
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
                    f"{self.project_id}_shot_{shot_index:04d}",
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

