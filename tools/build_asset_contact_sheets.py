from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path.cwd()
PROJECT_ID = "franklin"

IMAGE_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "02_Images"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "asset_intelligence"
)

MANIFEST_PATH = OUTPUT_DIR / "asset_contact_manifest.json"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

THUMB_WIDTH = 320
THUMB_HEIGHT = 180
LABEL_HEIGHT = 76
CELL_WIDTH = 340
CELL_HEIGHT = THUMB_HEIGHT + LABEL_HEIGHT

COLUMNS = 4
ROWS = 4
ITEMS_PER_SHEET = COLUMNS * ROWS


def safe_font(size: int):
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)

    return ImageFont.load_default()


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    max_lines: int = 3,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), candidate, font=font)

        if box[2] - box[0] <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)

        current = word

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        lines[-1] = lines[-1].rstrip(".") + "…"

    return lines


def main() -> None:
    if not IMAGE_DIR.exists():
        raise FileNotFoundError(
            f"Папка изображений не найдена: {IMAGE_DIR}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    images = sorted(
        [
            path
            for path in IMAGE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda path: path.name.lower(),
    )

    if not images:
        raise RuntimeError("В папке нет изображений.")

    font_id = safe_font(21)
    font_name = safe_font(15)

    manifest: list[dict[str, object]] = []

    total_sheets = math.ceil(
        len(images) / ITEMS_PER_SHEET
    )

    for sheet_index in range(total_sheets):
        sheet = Image.new(
            "RGB",
            (
                COLUMNS * CELL_WIDTH,
                ROWS * CELL_HEIGHT,
            ),
            "white",
        )

        draw = ImageDraw.Draw(sheet)

        start = sheet_index * ITEMS_PER_SHEET
        end = min(
            start + ITEMS_PER_SHEET,
            len(images),
        )

        for local_index, path in enumerate(
            images[start:end]
        ):
            asset_index = start + local_index + 1

            column = local_index % COLUMNS
            row = local_index // COLUMNS

            x = column * CELL_WIDTH
            y = row * CELL_HEIGHT

            try:
                with Image.open(path) as source:
                    source = ImageOps.exif_transpose(source)
                    source = source.convert("RGB")

                    thumb = ImageOps.fit(
                        source,
                        (THUMB_WIDTH, THUMB_HEIGHT),
                        method=Image.Resampling.LANCZOS,
                    )

            except Exception as exc:
                thumb = Image.new(
                    "RGB",
                    (THUMB_WIDTH, THUMB_HEIGHT),
                    "#dddddd",
                )

                error_draw = ImageDraw.Draw(thumb)
                error_draw.text(
                    (10, 70),
                    "IMAGE ERROR",
                    fill="black",
                    font=font_id,
                )

                print(f"Ошибка изображения {path}: {exc}")

            thumb_x = x + 10
            thumb_y = y + 10

            sheet.paste(
                thumb,
                (thumb_x, thumb_y),
            )

            draw.rectangle(
                [
                    thumb_x,
                    thumb_y,
                    thumb_x + THUMB_WIDTH,
                    thumb_y + THUMB_HEIGHT,
                ],
                outline="black",
                width=2,
            )

            asset_id = f"AZ-{asset_index:03d}"

            draw.rectangle(
                [
                    thumb_x,
                    thumb_y,
                    thumb_x + 92,
                    thumb_y + 34,
                ],
                fill="black",
            )

            draw.text(
                (thumb_x + 7, thumb_y + 4),
                asset_id,
                fill="white",
                font=font_id,
            )

            filename_lines = wrap_text(
                draw,
                path.name,
                font_name,
                THUMB_WIDTH,
                max_lines=3,
            )

            text_y = thumb_y + THUMB_HEIGHT + 7

            for line in filename_lines:
                draw.text(
                    (thumb_x, text_y),
                    line,
                    fill="black",
                    font=font_name,
                )
                text_y += 18

            manifest.append(
                {
                    "asset_code": asset_id,
                    "filename": path.name,
                    "path": str(path.resolve()),
                    "sheet": sheet_index + 1,
                    "position": local_index + 1,
                    "semantic_description": None,
                    "tags": [],
                    "objects": [],
                    "location": None,
                    "period": None,
                    "shot_scale": None,
                    "emotion": None,
                    "recommended_visual_needs": [],
                    "exclude_visual_needs": [],
                }
            )

        output_path = (
            OUTPUT_DIR
            / f"asset_contact_sheet_{sheet_index + 1:02d}.jpg"
        )

        sheet.save(
            output_path,
            quality=92,
        )

        print(
            f"Создан лист {sheet_index + 1}/{total_sheets}: "
            f"{output_path}"
        )

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "asset_count": len(manifest),
                "sheets": total_sheets,
                "assets": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 68)
    print("ASSET INTELLIGENCE CONTACT PACK")
    print("=" * 68)
    print("Изображений:", len(manifest))
    print("Контактных листов:", total_sheets)
    print("Папка:", OUTPUT_DIR)
    print("Manifest:", MANIFEST_PATH)


if __name__ == "__main__":
    main()
