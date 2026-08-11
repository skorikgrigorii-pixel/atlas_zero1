from pathlib import Path

from az_enterprise.core.promotion_narration_source_rc1 import (
    PromotionNarrationSourceRC1,
)


def test_promotion_narration_source_reads_real_narrator_text(
    tmp_path: Path,
):

    script = (
        tmp_path
        / "production_script.txt"
    )

    script.write_text(
        """
СЦЕНА 1

2. Продолжительность
00:00–00:30

3. Цель сцены
Редакторская цель.

4. Текст диктора
В Арктике есть места, где человек исчезает не сразу.
Сначала пропадает корабль.
Потом — голос.

5. Подробный видеоряд
Лёд.
Корабль.

СЦЕНА 2

2. Продолжительность
00:00–00:20

3. Цель сцены
Другая редакторская цель.

4. Текст диктора
Но спустя годы поисков появилась первая настоящая улика.

5. Подробный видеоряд
Архив.
""".strip(),
        encoding="utf-8",
    )

    source = PromotionNarrationSourceRC1(
        project_id="movie",
        root=tmp_path,
        script_path=script,
    )

    scenes = source.load()

    assert len(scenes) == 2

    assert scenes[0].source_start_sec == 0
    assert scenes[0].source_end_sec == 30

    assert scenes[1].source_start_sec == 30
    assert scenes[1].source_end_sec == 50

    assert (
        "Сначала пропадает корабль"
        in scenes[0].narration_text
    )

    assert (
        "Редакторская цель"
        not in scenes[0].narration_text
    )


def test_promotion_narration_source_aligns_to_movie_duration(
    tmp_path: Path,
):

    script = tmp_path / "script.txt"

    script.write_text(
        """
СЦЕНА 1
2. Продолжительность
00:00–00:20
4. Текст диктора
Первый текст.
5. Подробный видеоряд

СЦЕНА 2
2. Продолжительность
00:00–00:20
4. Текст диктора
Второй текст.
5. Подробный видеоряд
""".strip(),
        encoding="utf-8",
    )

    source = PromotionNarrationSourceRC1(
        project_id="movie",
        root=tmp_path,
        script_path=script,
    )

    scenes = source.aligned(
        target_duration_sec=80,
    )

    assert scenes[-1].source_end_sec == 80
    assert scenes[0].source_end_sec == 40
