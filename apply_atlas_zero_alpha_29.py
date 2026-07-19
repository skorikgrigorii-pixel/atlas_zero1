from __future__ import annotations

import ast
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


DATABASE_TARGET = Path("src/az_enterprise/core/database.py")
TEST_TARGET = Path("tests/test_database_lifecycle_alpha29.py")

TEST_MODULES = [
    "tests.test_database_lifecycle_alpha29",
    "tests.test_postproduction_quality_rc2",
    "tests.test_postproduction_rhythm_alpha271",
    "tests.test_postproduction_visual_alpha272",
    "tests.test_project_profiles_alpha273",
    "tests.test_recommendation_engine_alpha28",
    "tests.test_director_ai_alpha25",
]

LIFECYCLE_METHODS = r'''
    def close(self) -> None:
        """Close the underlying database connection safely and idempotently."""
        connection = getattr(self, "conn", None)
        if connection is None:
            return
        try:
            connection.close()
        finally:
            self.conn = None

    def __enter__(self):
        """Support deterministic database cleanup with a context manager."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.close()
        return False

    def __del__(self) -> None:
        """Best-effort fallback for callers that forgot to close explicitly."""
        try:
            self.close()
        except Exception:
            pass
'''

TEST_CONTENT = r'''from __future__ import annotations

import ast
import gc
import importlib
import sqlite3
import unittest
import warnings
from pathlib import Path


DATABASE_PATH = Path("src/az_enterprise/core/database.py")


def _database_classes():
    module = importlib.import_module("az_enterprise.core.database")
    source = DATABASE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if "self.conn" in segment and "sqlite3" in source:
            names.append(node.name)

    return [
        getattr(module, name)
        for name in names
        if hasattr(module, name)
    ]


class DatabaseLifecycleAlpha29Test(unittest.TestCase):
    def test_database_classes_expose_lifecycle_contract(self):
        classes = _database_classes()
        self.assertTrue(classes, "No database wrapper class detected.")

        for cls in classes:
            self.assertTrue(hasattr(cls, "close"))
            self.assertTrue(hasattr(cls, "__enter__"))
            self.assertTrue(hasattr(cls, "__exit__"))
            self.assertTrue(hasattr(cls, "__del__"))

    def test_close_is_idempotent_without_constructor(self):
        classes = _database_classes()
        for cls in classes:
            instance = cls.__new__(cls)
            instance.conn = sqlite3.connect(":memory:")
            instance.close()
            self.assertIsNone(instance.conn)
            instance.close()
            self.assertIsNone(instance.conn)

    def test_context_manager_closes_connection(self):
        classes = _database_classes()
        for cls in classes:
            instance = cls.__new__(cls)
            connection = sqlite3.connect(":memory:")
            instance.conn = connection

            with instance as opened:
                self.assertIs(opened, instance)
                opened.conn.execute("SELECT 1").fetchone()

            self.assertIsNone(instance.conn)
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_destructor_fallback_closes_connection_without_resource_warning(self):
        classes = _database_classes()
        for cls in classes:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                instance = cls.__new__(cls)
                instance.conn = sqlite3.connect(":memory:")
                instance.__del__()
                del instance
                gc.collect()

            resource_warnings = [
                item
                for item in caught
                if issubclass(item.category, ResourceWarning)
            ]
            self.assertEqual(resource_warnings, [])


if __name__ == "__main__":
    unittest.main()
'''


def find_database_classes(source: str) -> list[ast.ClassDef]:
    tree = ast.parse(source)
    candidates: list[ast.ClassDef] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        segment = ast.get_source_segment(source, node) or ""
        if "self.conn" in segment and (
            "sqlite3.connect" in segment
            or "self.conn =" in segment
        ):
            candidates.append(node)

    return candidates


def class_method_names(node: ast.ClassDef) -> set[str]:
    return {
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def patch_database_source(source: str) -> tuple[str, list[str]]:
    candidates = find_database_classes(source)
    if not candidates:
        raise RuntimeError(
            "No class owning self.conn was detected in database.py."
        )

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, str]] = []
    patched_classes: list[str] = []

    required_methods = {"close", "__enter__", "__exit__", "__del__"}

    for node in candidates:
        existing = class_method_names(node)
        missing = required_methods - existing
        if not missing:
            continue

        if existing & required_methods:
            raise RuntimeError(
                f"Class {node.name} has a partial lifecycle implementation. "
                "Manual review is required to avoid overriding existing behavior."
            )

        insertion_line = node.end_lineno
        if insertion_line is None:
            raise RuntimeError(
                f"Unable to determine the end of class {node.name}."
            )

        insertions.append((insertion_line, "\n" + LIFECYCLE_METHODS))
        patched_classes.append(node.name)

    if not patched_classes:
        return source, []

    for line_number, block in sorted(insertions, reverse=True):
        lines.insert(line_number, block)

    patched = "".join(lines)
    ast.parse(patched)
    return patched, patched_classes


def create_backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.alpha29.{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def restore(
    path: Path,
    backup: Path | None,
    existed_before: bool,
) -> None:
    if backup and backup.exists():
        shutil.copy2(backup, path)
    elif not existed_before and path.exists():
        path.unlink()


def run_tests() -> tuple[bool, str]:
    env = os.environ.copy()
    src = str(Path("src").resolve())
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src + os.pathsep + current if current else src
    )
    env["PYTHONWARNINGS"] = "error::ResourceWarning"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            *TEST_MODULES,
            "-v",
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def main() -> int:
    if not DATABASE_TARGET.exists():
        print(f"ERROR: file not found: {DATABASE_TARGET}")
        return 1

    required = [
        Path("src/az_enterprise/core/project_profiles_alpha273.py"),
        Path("src/az_enterprise/core/recommendation_engine_alpha28.py"),
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        print("ERROR: Alpha 2.8 installation was not detected.")
        for path in missing:
            print(f"Missing: {path}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tracked = [DATABASE_TARGET, TEST_TARGET]
    existed_before = {path: path.exists() for path in tracked}
    backups = {
        path: create_backup(path, stamp)
        for path in tracked
    }

    try:
        original = DATABASE_TARGET.read_text(encoding="utf-8")
        patched, patched_classes = patch_database_source(original)

        compile(patched, str(DATABASE_TARGET), "exec")
        compile(TEST_CONTENT, str(TEST_TARGET), "exec")

        DATABASE_TARGET.write_text(
            patched,
            encoding="utf-8",
            newline="\n",
        )
        TEST_TARGET.write_text(
            TEST_CONTENT,
            encoding="utf-8",
            newline="\n",
        )

        passed, output = run_tests()
        print(output)
        if not passed:
            raise RuntimeError(
                "One or more tests failed or a ResourceWarning was raised."
            )

    except Exception as exc:
        for path in tracked:
            restore(path, backups[path], existed_before[path])
        print(f"ERROR: {exc}")
        print("Rollback completed. Original files restored.")
        return 1

    print("ATLAS ZERO Alpha 2.9 Stability & Infrastructure applied successfully.")
    if patched_classes:
        print("Database lifecycle added to:")
        for name in patched_classes:
            print(f"- {name}")
    else:
        print("Database lifecycle was already fully implemented.")

    for path in tracked:
        backup = backups[path]
        if backup:
            print(f"Backup: {backup}")
        else:
            print(f"Backup not required (new file): {path}")

    print(f"Test modules passed: {len(TEST_MODULES)}")
    print("ResourceWarning gate: enabled")
    print("Lifecycle contract:")
    print("- close()")
    print("- context manager support")
    print("- idempotent cleanup")
    print("- destructor fallback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
