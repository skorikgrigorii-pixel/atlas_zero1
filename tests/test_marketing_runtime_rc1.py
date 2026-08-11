import sqlite3
from pathlib import Path

from az_enterprise.core.marketing_runtime_rc1 import (
    MarketingRuntimeRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")

    def init(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()
        return None

    def execute(self, sql, params=()):
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor

    def executemany(self, sql, params):
        cursor = self.conn.executemany(
            sql,
            params,
        )
        self.conn.commit()
        return cursor

    def executescript(self, sql):
        cursor = self.conn.executescript(sql)
        self.conn.commit()
        return cursor


def test_marketing_runtime_rc1(tmp_path: Path):

    db = DB()
    db.init()

    runtime = MarketingRuntimeRC1(
        db=db,
        project_id="movie",
        root=tmp_path,
    )

    result = runtime.record(
        platform="youtube",
        metrics={
            "views": 100,
            "impressions": 1000,
            "ctr": 0.05,
            "watch_time_sec": 5000,
            "avg_view_duration_sec": 50,
            "likes": 10,
            "comments": 2,
            "shares": 1,
            "subscribers_delta": 3,
        },
        captured_at=
            "2026-01-01T00:00:00+00:00",
    )

    assert (
        result["state"]
        == "MARKETING_RUNTIME_COMPLETE"
    )

    assert result["platform"] == "youtube"

    assert Path(
        result["artifact"]
    ).is_file()
