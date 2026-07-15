from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable, Any
from .paths import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  duration_sec REAL DEFAULT 960,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS assets(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  filename TEXT NOT NULL,
  media_type TEXT NOT NULL,
  sha256 TEXT,
  category TEXT,
  tags TEXT,
  emotion TEXT,
  quality REAL DEFAULT 0,
  width INTEGER,
  height INTEGER,
  duration_sec REAL,
  duplicate_of TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shots(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  idx INTEGER NOT NULL,
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  block TEXT,
  story_goal TEXT,
  visual_need TEXT,
  emotion TEXT,
  status TEXT DEFAULT 'missing',
  assigned_asset_id TEXT,
  transition TEXT DEFAULT 'dissolve',
  camera_motion TEXT DEFAULT 'slow push-in'
);
CREATE TABLE IF NOT EXISTS director_decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  shot_id TEXT NOT NULL,
  asset_id TEXT,
  score REAL NOT NULL,
  reason TEXT NOT NULL,
  alternatives TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS workflow_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  details TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS integration_profiles(
  id TEXT PRIMARY KEY,
  service TEXT NOT NULL,
  status TEXT NOT NULL,
  env_key TEXT,
  capabilities TEXT,
  last_check TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS api_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  service TEXT NOT NULL,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  payload TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS quality_reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  readiness REAL,
  coverage REAL,
  duplicate_count INTEGER,
  missing_count INTEGER,
  summary TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS visual_profiles(
  asset_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  style_score REAL DEFAULT 0,
  plan_type TEXT,
  palette TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS integration_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  service TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  request_json TEXT,
  response_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS workflow_steps(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  step_key TEXT NOT NULL,
  title TEXT NOT NULL,
  depends_on TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  result_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS production_snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS asset_similarity(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  asset_id_a TEXT NOT NULL,
  asset_id_b TEXT NOT NULL,
  score REAL NOT NULL,
  reason TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS api_credentials_checks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  service TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operator_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 3,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  owner TEXT DEFAULT 'operator',
  details TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS runbook_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  step_no INTEGER NOT NULL,
  action TEXT NOT NULL,
  expected_result TEXT,
  artifact_path TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS export_validations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  artifact TEXT NOT NULL,
  exists_flag INTEGER NOT NULL,
  size_bytes INTEGER DEFAULT 0,
  comment TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS readiness_checks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  criterion TEXT NOT NULL,
  score REAL NOT NULL,
  passed INTEGER NOT NULL,
  comment TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row

    def _migrate_assets_project_scoped_path(self) -> None:
        """Make asset paths unique inside a project, not globally.

        The migration supports both legacy extended databases and newly
        created minimal test databases. Missing optional columns are filled
        with safe defaults during the table rebuild.
        """
        table_row = self.one(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type='table'
              AND name='assets'
            """
        )

        if table_row is None:
            return

        table_sql = str(table_row["sql"] or "")
        normalized_sql = " ".join(
            table_sql.lower().split()
        )

        has_global_path_unique = (
            "path text not null unique" in normalized_sql
            or "unique(path)" in normalized_sql
        )

        if not has_global_path_unique:
            return

        existing_columns = {
            str(row["name"])
            for row in self.rows(
                "PRAGMA table_info(assets)"
            )
        }

        required_columns = {
            "id",
            "project_id",
            "path",
            "filename",
            "media_type",
        }

        missing_required = (
            required_columns - existing_columns
        )

        if missing_required:
            raise RuntimeError(
                "Cannot migrate assets table; "
                "required columns are missing: "
                + ", ".join(sorted(missing_required))
            )

        column_defaults = {
            "id": "id",
            "project_id": "project_id",
            "path": "path",
            "filename": "filename",
            "media_type": "media_type",
            "sha256": (
                "sha256"
                if "sha256" in existing_columns
                else "NULL"
            ),
            "category": (
                "category"
                if "category" in existing_columns
                else "NULL"
            ),
            "tags": (
                "tags"
                if "tags" in existing_columns
                else "NULL"
            ),
            "emotion": (
                "emotion"
                if "emotion" in existing_columns
                else "NULL"
            ),
            "quality": (
                "quality"
                if "quality" in existing_columns
                else "0"
            ),
            "width": (
                "width"
                if "width" in existing_columns
                else "NULL"
            ),
            "height": (
                "height"
                if "height" in existing_columns
                else "NULL"
            ),
            "duration_sec": (
                "duration_sec"
                if "duration_sec" in existing_columns
                else "NULL"
            ),
            "duplicate_of": (
                "duplicate_of"
                if "duplicate_of" in existing_columns
                else "NULL"
            ),
            "created_at": (
                "created_at"
                if "created_at" in existing_columns
                else "CURRENT_TIMESTAMP"
            ),
            "semantic_class": (
                "semantic_class"
                if "semantic_class" in existing_columns
                else "NULL"
            ),
            "semantic_description": (
                "semantic_description"
                if "semantic_description" in existing_columns
                else "NULL"
            ),
            "visual_group": (
                "visual_group"
                if "visual_group" in existing_columns
                else "NULL"
            ),
            "perceptual_hash": (
                "perceptual_hash"
                if "perceptual_hash" in existing_columns
                else "NULL"
            ),
            "semantic_confidence": (
                "semantic_confidence"
                if "semantic_confidence" in existing_columns
                else "0"
            ),
            "max_use": (
                "max_use"
                if "max_use" in existing_columns
                else "3"
            ),
        }

        destination_columns = list(
            column_defaults.keys()
        )

        select_expressions = [
            column_defaults[column]
            for column in destination_columns
        ]

        destination_sql = ",\n                    ".join(
            destination_columns
        )

        select_sql = ",\n                    ".join(
            select_expressions
        )

        self.conn.execute(
            "PRAGMA foreign_keys=OFF"
        )

        try:
            self.conn.execute("BEGIN")

            self.conn.execute(
                """
                DROP TABLE IF EXISTS
                assets_rc2_migration
                """
            )

            self.conn.execute(
                """
                CREATE TABLE assets_rc2_migration(
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    sha256 TEXT,
                    category TEXT,
                    tags TEXT,
                    emotion TEXT,
                    quality REAL DEFAULT 0,
                    width INTEGER,
                    height INTEGER,
                    duration_sec REAL,
                    duplicate_of TEXT,
                    created_at TEXT
                        DEFAULT CURRENT_TIMESTAMP,
                    semantic_class TEXT,
                    semantic_description TEXT,
                    visual_group TEXT,
                    perceptual_hash TEXT,
                    semantic_confidence REAL
                        DEFAULT 0,
                    max_use INTEGER DEFAULT 3,
                    UNIQUE(project_id, path)
                )
                """
            )

            self.conn.execute(
                f"""
                INSERT INTO assets_rc2_migration(
                    {destination_sql}
                )
                SELECT
                    {select_sql}
                FROM assets
                """
            )

            self.conn.execute(
                "DROP TABLE assets"
            )

            self.conn.execute(
                """
                ALTER TABLE assets_rc2_migration
                RENAME TO assets
                """
            )

            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_assets_project_media_type
                ON assets(
                    project_id,
                    media_type
                )
                """
            )

            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_assets_project_sha256
                ON assets(
                    project_id,
                    sha256
                )
                """
            )

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

        finally:
            self.conn.execute(
                "PRAGMA foreign_keys=ON"
            )



    def init(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate_assets_project_scoped_path()

    def execute(self, sql: str, params: Iterable[Any] = ()): 
        cur = self.conn.execute(sql, tuple(params))
        self.conn.commit()
        return cur

    def many(self, sql: str, params: Iterable[Iterable[Any]]):
        cur = self.conn.executemany(sql, params)
        self.conn.commit()
        return cur

    def rows(self, sql: str, params: Iterable[Any] = ()): 
        return list(self.conn.execute(sql, tuple(params)))

    def one(self, sql: str, params: Iterable[Any] = ()): 
        return self.conn.execute(sql, tuple(params)).fetchone()

    def close(self):
        self.conn.close()
