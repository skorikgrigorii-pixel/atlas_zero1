from pathlib import Path

src = Path("FILM10_CANONICAL_IMPORT_V1_4.py")
dst = Path("FILM10_CANONICAL_IMPORT_V1_5.py")

if not src.exists():
    raise FileNotFoundError(src)

text = src.read_text(encoding="utf-8-sig")

old_func = '''def project_asset_id(digest):
    raw = PROJECT_ID + "\\0" + digest
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
'''

new_func = '''def project_asset_id(digest, path):
    try:
        rel = path.resolve().relative_to(PROJECT.resolve())
        identity = rel.as_posix().lower()
    except Exception:
        identity = str(path.resolve()).lower()

    raw = PROJECT_ID + "\\0" + digest + "\\0" + identity
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
'''

if old_func not in text:
    raise RuntimeError(
        "Expected project_asset_id() block not found. "
        "V1.4 source differs from expected version."
    )

text = text.replace(
    old_func,
    new_func,
    1,
)

old_call = '''    asset_id = project_asset_id(digest)
'''

new_call = '''    asset_id = project_asset_id(digest, p)
'''

if old_call not in text:
    raise RuntimeError(
        "Expected asset ID call not found."
    )

text = text.replace(
    old_call,
    new_call,
    1,
)

old_seen = '''    if digest not in seen_hash:
        seen_hash[digest] = asset_id
'''

new_seen = '''    if digest not in seen_hash:
        seen_hash[digest] = asset_id
'''

if old_seen not in text:
    raise RuntimeError(
        "Expected duplicate tracking block not found."
    )

old_gate = '''if len({a["id"] for a in assets}) != 60:
    raise RuntimeError("Asset ID collision/duplicate detected")
'''

new_gate = '''unique_asset_ids = len({a["id"] for a in assets})
duplicate_files = sum(1 for a in assets if a["duplicate_of"])

print("UNIQUE ASSET IDS      :", unique_asset_ids)
print("CONTENT DUPLICATES    :", duplicate_files)

if unique_asset_ids != 60:
    raise RuntimeError(
        "Physical asset ID collision detected: "
        "{} unique IDs for 60 files".format(unique_asset_ids)
    )
'''

if old_gate not in text:
    raise RuntimeError(
        "Expected V1.4 asset gate not found."
    )

text = text.replace(
    old_gate,
    new_gate,
    1,
)

text = text.replace(
    "ATLAS ZERO — FILM10 CANONICAL IMPORT V1.4",
    "ATLAS ZERO — FILM10 CANONICAL IMPORT V1.5",
)

text = text.replace(
    "atlas_zero.film10_canonical_import.v1.4",
    "atlas_zero.film10_canonical_import.v1.5",
)

text = text.replace(
    "FILM10_CANONICAL_IMPORT_REPORT_V1_4.json",
    "FILM10_CANONICAL_IMPORT_REPORT_V1_5.json",
)

text = text.replace(
    "FILM10_CANONICAL_SHOTS_V1_4.json",
    "FILM10_CANONICAL_SHOTS_V1_5.json",
)

text = text.replace(
    "FILM10_CANONICAL_SCENES_V1_4.json",
    "FILM10_CANONICAL_SCENES_V1_5.json",
)

text = text.replace(
    "FILM10_CANONICAL_ASSETS_V1_4.json",
    "FILM10_CANONICAL_ASSETS_V1_5.json",
)

text = text.replace(
    "FILM10 CANONICAL IMPORT V1.4: PASS",
    "FILM10 CANONICAL IMPORT V1.5: PASS",
)

dst.write_text(
    text,
    encoding="utf-8",
)

print("=" * 100)
print("FILM10 CANONICAL IMPORT PATCH V1.4 -> V1.5")
print("=" * 100)
print("SOURCE :", src.resolve())
print("OUTPUT :", dst.resolve())
print()
print("CHANGE:")
print("  physical file identity -> unique asset.id")
print("  SHA256                -> content identity")
print("  duplicate_of          -> duplicate relationship")
print("  60 files              -> remain 60 canonical asset rows")
print()
print("PATCH: PASS")
