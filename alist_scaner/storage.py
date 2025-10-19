"""SQLite 持久化存储模块。"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

from .models import Episode, ShowMetadata


@dataclass
class SQLiteStore:
    """负责管理剧集与目录的持久化信息。"""

    db_path: str

    def __post_init__(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._bootstrap()

    def _bootstrap(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;

            CREATE TABLE IF NOT EXISTS shows (
                path TEXT PRIMARY KEY,
                last_scan_ts INTEGER NOT NULL,
                last_remote_lastmod TEXT
            );

            CREATE TABLE IF NOT EXISTS episodes (
                path TEXT PRIMARY KEY,
                show_path TEXT NOT NULL,
                lang TEXT,
                filename TEXT,
                size INTEGER,
                lastmod TEXT,
                etag TEXT,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS show_metadata (
                show_path TEXT PRIMARY KEY,
                title TEXT,
                lang TEXT,
                rating REAL,
                overview TEXT,
                genres TEXT,
                source TEXT,
                updated_at INTEGER NOT NULL
            );
            """
        )
        self._conn.commit()

    def get_show_metadata(self, show_path: str) -> Optional[ShowMetadata]:
        cursor = self._conn.execute(
            "SELECT show_path, title, lang, rating, overview, genres, source, updated_at"
            " FROM show_metadata WHERE show_path = ?",
            (show_path,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        genres: list[str] = []
        if row["genres"]:
            try:
                genres = json.loads(row["genres"])
                if not isinstance(genres, list):
                    genres = []
            except json.JSONDecodeError:
                genres = []
        return ShowMetadata(
            show_path=row["show_path"],
            title=row["title"] or "",
            lang=row["lang"] or "",
            rating=row["rating"],
            overview=row["overview"],
            genres=genres,
            source=row["source"] or "",
            updated_at=row["updated_at"],
        )

    def should_skip_scan(
        self,
        path: str,
        remote_lastmod: Optional[str],
        cache_ttl_seconds: int,
    ) -> bool:
        """判断目录是否可跳过扫描。"""

        cursor = self._conn.execute(
            "SELECT last_scan_ts, last_remote_lastmod FROM shows WHERE path = ?",
            (path,),
        )
        row = cursor.fetchone()
        if row is None:
            return False

        last_scan_ts = row["last_scan_ts"]
        last_remote_lastmod = row["last_remote_lastmod"] or ""
        now_ts = int(time.time())

        if remote_lastmod and last_remote_lastmod and remote_lastmod != last_remote_lastmod:
            # 远端目录有更新，必须重新扫描
            return False

        if remote_lastmod and last_remote_lastmod and remote_lastmod == last_remote_lastmod:
            if cache_ttl_seconds > 0 and now_ts - last_scan_ts < cache_ttl_seconds:
                return True
            return False

        if cache_ttl_seconds > 0 and now_ts - last_scan_ts < cache_ttl_seconds:
            return True

        return False

    def mark_directory_scanned(self, path: str, remote_lastmod: Optional[str]) -> None:
        now_ts = int(time.time())
        self._conn.execute(
            """
            INSERT INTO shows(path, last_scan_ts, last_remote_lastmod)
            VALUES(?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                last_scan_ts = excluded.last_scan_ts,
                last_remote_lastmod = excluded.last_remote_lastmod
            """,
            (path, now_ts, remote_lastmod or ""),
        )
        self._conn.commit()

    def upsert_episodes(self, episodes: Iterable[Episode]) -> None:
        now_ts = int(time.time())
        rows = [
            (
                episode.path,
                episode.show_path,
                episode.lang,
                episode.filename,
                episode.size,
                episode.lastmod,
                episode.etag,
                now_ts,
            )
            for episode in episodes
        ]
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT INTO episodes(path, show_path, lang, filename, size, lastmod, etag, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                show_path = excluded.show_path,
                lang = excluded.lang,
                filename = excluded.filename,
                size = excluded.size,
                lastmod = excluded.lastmod,
                etag = excluded.etag,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        self._conn.commit()

    def upsert_show_metadata(self, metadata: ShowMetadata) -> None:
        now_ts = int(time.time())
        genres = json.dumps(metadata.genres, ensure_ascii=False) if metadata.genres else "[]"
        self._conn.execute(
            """
            INSERT INTO show_metadata(show_path, title, lang, rating, overview, genres, source, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(show_path) DO UPDATE SET
                title = excluded.title,
                lang = excluded.lang,
                rating = excluded.rating,
                overview = excluded.overview,
                genres = excluded.genres,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                metadata.show_path,
                metadata.title,
                metadata.lang,
                metadata.rating,
                metadata.overview,
                genres,
                metadata.source,
                now_ts,
            ),
        )
        self._conn.commit()

    def iter_show_entries(self) -> Iterator[Tuple[str, str]]:
        """返回数据库中已记录的剧集路径及其语言。"""

        cursor = self._conn.execute(
            """
            SELECT e.show_path, COALESCE(e.lang, '') AS lang
            FROM episodes e
            INNER JOIN (
                SELECT show_path, MAX(updated_at) AS updated_at
                FROM episodes
                GROUP BY show_path
            ) latest
            ON e.show_path = latest.show_path AND e.updated_at = latest.updated_at
            GROUP BY e.show_path
            ORDER BY e.show_path
            """
        )
        for row in cursor:
            yield (row["show_path"], row["lang"])

    def close(self) -> None:
        self._conn.close()
