from pathlib import Path

path = Path(
    r".\src\az_enterprise\core\promotion_narration_alignment_rc1.py"
)

text = path.read_text(
    encoding="utf-8-sig"
)

old = '''        value = (
            " ".join(
                line.strip().split()
            )
        )

        prefix = "\\u0441\\u0446\\u0435\\u043d\\u0430"

        lowered = value.lower()
'''

new = '''        value = (
            " ".join(
                line.strip().split()
            )
        )

        # RC2 textual Production Script:
        # scene_001, scene_002, ...
        rc2_match = re.fullmatch(
            r"scene[_\\s-]?(\\d+)",
            value,
            flags=re.IGNORECASE,
        )

        if rc2_match:
            return int(
                rc2_match.group(1)
            )

        prefix = "\\u0441\\u0446\\u0435\\u043d\\u0430"

        lowered = value.lower()
'''

if old not in text:
    raise SystemExit(
        "TARGET BLOCK NOT FOUND"
    )

path.write_text(
    text.replace(old, new, 1),
    encoding="utf-8",
)

print("RC2 SCENE HEADING PATCH: OK")
