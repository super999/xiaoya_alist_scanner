"""剧集元数据抓取与更新流程。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable

from .config import Config
from .metadata import ShowMetadataFetcher, derive_title_from_path
from .storage import SQLiteStore


@dataclass
class ShowEntry:
    """代表一个待抓取元数据的剧集。"""

    show_path: str
    lang: str


class MetadataUpdater:
    """根据已扫描的剧集记录抓取元数据并写入数据库。"""

    def __init__(self, config: Config, storage: SQLiteStore, fetcher: ShowMetadataFetcher) -> None:
        self.config = config
        self.storage = storage
        self.fetcher = fetcher
        self._cache_ttl = max(self.config.metadata_cache_hours, 0) * 3600

    def run(self) -> None:
        shows = list(self._iter_shows())
        if not shows:
            logging.info("数据库中没有可用于抓取的剧集记录，请先运行扫描任务。")
            return

        updated = 0
        skipped = 0
        failed = 0

        for entry in shows:
            if not self._should_fetch(entry.show_path):
                skipped += 1
                continue

            title = derive_title_from_path(entry.show_path)
            if not title:
                logging.debug("无法从路径推导剧名，跳过：%s", entry.show_path)
                skipped += 1
                continue

            lang_hint = entry.lang or "美剧"
            metadata = self.fetcher.fetch(title=title, lang=lang_hint)
            if not metadata:
                failed += 1
                continue

            metadata.show_path = entry.show_path
            metadata.lang = lang_hint
            self.storage.upsert_show_metadata(metadata)
            updated += 1

            logging.info(
                "已更新《%s》(%s) 的元数据。",
                metadata.title or title,
                entry.show_path,
            )

        logging.info(
            "元数据抓取完成：总计 %s，更新 %s，跳过 %s，失败 %s。",
            len(shows),
            updated,
            skipped,
            failed,
        )

    def _iter_shows(self) -> Iterable[ShowEntry]:
        for show_path, lang in self.storage.iter_show_entries():
            yield ShowEntry(show_path=show_path, lang=lang)

    def _should_fetch(self, show_path: str) -> bool:
        cached = self.storage.get_show_metadata(show_path)
        if cached is None:
            return True

        needs_refresh = cached.rating is None or not cached.overview or not cached.genres
        if needs_refresh:
            return True

        # if self._cache_ttl <= 0:
        #     return False

        age = int(time.time()) - cached.updated_at
        return age >= self._cache_ttl
