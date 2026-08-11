import json
from pathlib import Path

from az_enterprise.core.promotion_candidate_analyzer_rc1 import (
    PromotionCandidateAnalyzerRC1,
)

from az_enterprise.core.promotion_narration_alignment_rc1 import (
    PromotionNarrationAlignmentRC1,
)


def fake_alignment_result(
    self,
):
    return {
        "alignment_source":
            "test_alignment_fixture",

        "voice_duration_sec":
            144.0,

        "scenes": [
            {
                "scene": 1,
                "block": 1,
                "start_sec": 0.0,
                "end_sec": 48.0,
                "duration_sec": 48.0,
                "text":
                    (
                        "\u0412 \u0410\u0440\u043a\u0442\u0438\u043a\u0435 "
                        "\u0438\u0441\u0447\u0435\u0437\u043b\u0430 "
                        "\u044d\u043a\u0441\u043f\u0435\u0434\u0438\u0446\u0438\u044f. "
                        "\u041a\u043e\u0440\u0430\u0431\u043b\u0438 "
                        "\u043d\u0435 \u0432\u0435\u0440\u043d\u0443\u043b\u0438\u0441\u044c."
                    ),
            },
            {
                "scene": 2,
                "block": 1,
                "start_sec": 48.0,
                "end_sec": 96.0,
                "duration_sec": 48.0,
                "text":
                    (
                        "\u041f\u043e\u0438\u0441\u043a\u0438 "
                        "\u043d\u0430\u0447\u0430\u043b\u0438\u0441\u044c "
                        "\u0441\u043f\u0443\u0441\u0442\u044f "
                        "\u0433\u043e\u0434\u044b. "
                        "\u0410\u0440\u043a\u0442\u0438\u043a\u0430 "
                        "\u0445\u0440\u0430\u043d\u0438\u043b\u0430 "
                        "\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u0435."
                    ),
            },
            {
                "scene": 3,
                "block": 1,
                "start_sec": 96.0,
                "end_sec": 144.0,
                "duration_sec": 48.0,
                "text":
                    (
                        "\u041d\u0430\u0439\u0434\u0435\u043d\u043d\u0430\u044f "
                        "\u0437\u0430\u043f\u0438\u0441\u043a\u0430 "
                        "\u0438\u0437\u043c\u0435\u043d\u0438\u043b\u0430 "
                        "\u0432\u0441\u044e "
                        "\u0438\u0441\u0442\u043e\u0440\u0438\u044e."
                    ),
            },
        ],
    }


def build_timeline(
    path: Path,
):

    items = []

    stories = [
        "Обычная экспедиция начинается с надежды.",
        "Но никто ещё не знает, что впереди исчезнут 129 человек.",
        "Почему два корабля оказались заперты во льдах?",
        "Экспедиция теряет связь с внешним миром.",
        "Лёд становится смертельной ловушкой.",
        "До сих пор точного ответа на многие вопросы нет.",
        "Спасатели находят первые странные следы.",
        "Но главная загадка только начинается.",
        "Арктика скрывает последнее свидетельство экспедиции.",
        "Эта история изменила представление о полярных путешествиях.",
        "Следующая часть рассказывает о поисках кораблей.",
        "Экспедиция становится одной из величайших тайн XIX века.",
    ]

    visuals = [
        "Архивная карта Арктики",
        "Корабли во льдах",
        "Крупный план карты и маршрут экспедиции",
        "Шторм и ледяной океан",
        "Панорама льда, корабль в ловушке",
        "Архивные документы",
        "Следы на снегу",
        "Аэрофотосъёмка ледяной пустыни",
        "Корабль под водой",
        "Исторические фотографии",
        "Карта поисковой экспедиции",
        "Воздушная панорама Арктики",
    ]

    emotions = [
        "надежда",
        "опасность",
        "загадка",
        "страх",
        "смертельная опасность",
        "тайна",
        "тревога",
        "интрига",
        "трагедия",
        "размышление",
        "ожидание",
        "тайна",
    ]

    start = 0.0

    for index in range(12):

        end = start + 6.0

        items.append({
            "shot_id":
                f"shot_{index + 1:04d}",

            "start_sec":
                start,

            "end_sec":
                end,

            "story_goal":
                stories[index],

            "visual_need":
                visuals[index],

            "emotion":
                emotions[index],
        })

        start = end

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            {
                "items":
                    items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )



def build_production_script(
    root: Path,
) -> Path:

    path = (
        root
        / "workspace"
        / "projects"
        / "franklin"
        / "script"
        / "production_script.txt"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    scene = (
        "\u0421\u0426\u0415\u041d\u0410"
    )

    duration_label = (
        "2. "
        "\u041f\u0440\u043e\u0434\u043e\u043b\u0436"
        "\u0438\u0442\u0435\u043b\u044c\u043d\u043e"
        "\u0441\u0442\u044c"
    )

    goal_label = (
        "3. "
        "\u0426\u0435\u043b\u044c "
        "\u0441\u0446\u0435\u043d\u044b"
    )

    narrator_label = (
        "4. "
        "\u0422\u0435\u043a\u0441\u0442 "
        "\u0434\u0438\u043a\u0442\u043e\u0440\u0430"
    )

    visual_label = (
        "5. "
        "\u041f\u043e\u0434\u0440\u043e\u0431\u043d"
        "\u044b\u0439 "
        "\u0432\u0438\u0434\u0435\u043e\u0440\u044f"
        "\u0434"
    )

    fixture = f"""
{scene} 1

{duration_label}
00:00\u201300:24

{goal_label}
Editorial context one.

{narrator_label}
129 people entered the Arctic.
Nobody returned.
One of the greatest expeditions of the nineteenth century vanished.

{visual_label}
Ice.

{scene} 2

{duration_label}
00:00\u201300:24

{goal_label}
Editorial context two.

{narrator_label}
Why did two ships disappear among the ice?
Years later, search parties discovered disturbing evidence.

{visual_label}
Map.

{scene} 3

{duration_label}
00:00\u201300:24

{goal_label}
Editorial context three.

{narrator_label}
One of the strangest discoveries was a boat mounted on a sledge.
The men carried books and silver while dying in the cold.

{visual_label}
Boat.
""".strip()

    path.write_text(
        fixture,
        encoding="utf-8",
    )

    return path


def test_candidate_analyzer_finds_ranked_windows(
    tmp_path: Path,
    monkeypatch,
):

    timeline = (
        tmp_path
        / "timeline.json"
    )

    build_timeline(
        timeline
    )

    narration_script = build_production_script(
        tmp_path
    )

    assert narration_script.is_file()

    fixture_text = narration_script.read_text(
        encoding="utf-8-sig"
    )

    assert "\u0421\u0426\u0415\u041d\u0410 1" in fixture_text
    assert "\u0422\u0435\u043a\u0441\u0442 \u0434\u0438\u043a\u0442\u043e\u0440\u0430" in fixture_text

    monkeypatch.setattr(
        PromotionNarrationAlignmentRC1,
        "align",
        fake_alignment_result,
    )

    analyzer = (
        PromotionCandidateAnalyzerRC1(
            project_id="franklin",
            root=tmp_path,
            timeline_path=timeline,
            narration_script_path=narration_script,
        )
    )

    result = analyzer.analyze(
        top_k=5,
        min_duration_sec=18,
        target_duration_sec=30,
        max_duration_sec=42,
    )

    assert (
        result["state"]
        == "PROMOTION_CANDIDATES_READY"
    )

    assert (
        result["shots_analyzed"]
        == 12
    )

    assert (
        result["selected_candidates"]
        > 0
    )

    scores = [
        item["total_score"]
        for item in result[
            "candidates"
        ]
    ]

    assert scores == sorted(
        scores,
        reverse=True,
    )

    assert (
        result["candidates"][0][
            "duration_sec"
        ]
        >= 18
    )


def test_candidate_analyzer_produces_factory_contract(
    tmp_path: Path,
    monkeypatch,
):

    timeline = (
        tmp_path
        / "timeline.json"
    )

    build_timeline(
        timeline
    )

    narration_script = build_production_script(
        tmp_path
    )

    assert narration_script.is_file()

    fixture_text = narration_script.read_text(
        encoding="utf-8-sig"
    )

    assert "\u0421\u0426\u0415\u041d\u0410 1" in fixture_text
    assert "\u0422\u0435\u043a\u0441\u0442 \u0434\u0438\u043a\u0442\u043e\u0440\u0430" in fixture_text

    monkeypatch.setattr(
        PromotionNarrationAlignmentRC1,
        "align",
        fake_alignment_result,
    )

    analyzer = (
        PromotionCandidateAnalyzerRC1(
            project_id="franklin",
            root=tmp_path,
            timeline_path=timeline,
            narration_script_path=narration_script,
        )
    )

    result = analyzer.analyze(
        top_k=3,
    )

    candidates = (
        analyzer.promotion_candidates(
            result
        )
    )

    assert 1 <= len(candidates) <= 3

    assert (
        len(candidates)
        == result["selected_candidates"]
    )

    for candidate in candidates:
        assert (
            candidate.source_end_sec
            >
            candidate.source_start_sec
        )


def test_candidate_analyzer_respects_real_shot_boundaries(
    tmp_path: Path,
    monkeypatch,
):

    timeline = (
        tmp_path
        / "timeline.json"
    )

    build_timeline(
        timeline
    )

    narration_script = build_production_script(
        tmp_path
    )

    assert narration_script.is_file()

    fixture_text = narration_script.read_text(
        encoding="utf-8-sig"
    )

    assert "\u0421\u0426\u0415\u041d\u0410 1" in fixture_text
    assert "\u0422\u0435\u043a\u0441\u0442 \u0434\u0438\u043a\u0442\u043e\u0440\u0430" in fixture_text

    monkeypatch.setattr(
        PromotionNarrationAlignmentRC1,
        "align",
        fake_alignment_result,
    )

    analyzer = (
        PromotionCandidateAnalyzerRC1(
            project_id="franklin",
            root=tmp_path,
            timeline_path=timeline,
            narration_script_path=narration_script,
        )
    )

    result = analyzer.analyze(
        top_k=5,
    )

    valid_boundaries = {
        float(index * 6)
        for index in range(13)
    }

    for candidate in result[
        "candidates"
    ]:

        assert (
            candidate["start_sec"]
            in valid_boundaries
        )

        assert (
            candidate["end_sec"]
            in valid_boundaries
        )
