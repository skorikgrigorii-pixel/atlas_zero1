from pathlib import Path

path = Path(
    r".\src\az_enterprise\core\promotion_narration_alignment_rc1.py"
)

text = path.read_text(
    encoding="utf-8-sig"
)

old = '''        return (
            normalized.startswith("3.")
            or normalized.startswith("4.")
        ) and target in normalized
'''

new = '''        if normalized == "voiceover":
            return True

        return (
            normalized.startswith("3.")
            or normalized.startswith("4.")
        ) and target in normalized
'''

if old not in text:
    raise SystemExit("TARGET BLOCK NOT FOUND")

path.write_text(
    text.replace(old, new, 1),
    encoding="utf-8",
)

print("RC2 VOICEOVER MARKER PATCH: OK")
