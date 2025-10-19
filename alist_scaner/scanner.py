"""剧集扫描主逻辑。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple

from .config import Config
from .filters import EpisodeFilter
from .models import Episode, WebDAVResource
from .state import StateStore
from .storage import SQLiteStore
from .webdav import WebDAVClient


ShowBatch = Tuple[str, Optional[str], List[Episode]]


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    path = path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


@dataclass
class EpisodeScanner:
    """负责 orchestrate WebDAV 扫描流程。"""

    config: Config
    client: WebDAVClient
    state: StateStore
    filter: EpisodeFilter
    storage: SQLiteStore

    @property
    def _cache_ttl_seconds(self) -> int:
        hours = max(self.config.scan_cache_hours, 0)
        return hours * 3600

    def run(self) -> None:
        logging.info("开始扫描 WebDAV（小雅 Alist）...")

        state_cache = self.state.load()
        first_run = not bool(state_cache)
        if first_run and self.config.only_new:
            logging.info("首次运行：为了避免把历史内容都当作新增，本次不输出新增清单。")
        all_new: List[Episode] = []
        all_episodes: List[Episode] = []

        for cache_key, lastmod, episodes in self._iter_show_batches():
            if not episodes:
                self.storage.mark_directory_scanned(cache_key, lastmod)
                continue

            new_eps: List[Episode] = []
            for episode in episodes:
                is_new = self.state.detect_new(episode)
                if is_new and not first_run:
                    episode.is_new = True
                    new_eps.append(episode)
                self.state.mark_seen(episode)

            self.state.save()
            self.storage.upsert_episodes(episodes)
            self.storage.mark_directory_scanned(cache_key, lastmod)

            if self.config.only_new:
                all_new.extend(new_eps)
            else:
                all_episodes.extend(episodes)

            logging.debug(
                "剧集目录 %s 扫描完成，新增 %s 条，全部 %s 条。",
                episodes[0].show_path if episodes else cache_key,
                len(new_eps),
                len(episodes),
            )

        if self.config.only_new:
            payload = [episode.to_dict(include_is_new=True) for episode in all_new]
        else:
            payload = [episode.to_dict(include_is_new=True) for episode in all_episodes]

        print(json.dumps(payload, ensure_ascii=False, indent=2))

        logging.info(
            "扫描流程完成，输出 %s 条记录。",
            len(payload),
        )

    def _iter_show_batches(self) -> Iterator[ShowBatch]:
        """按照剧集目录逐个返回扫描结果。"""

        for root in self.config.roots:
            if self._is_path_skipped(root):
                logging.info("配置跳过根目录：%s", root)
                continue
            entries = self.client.list_directory(root, depth=1)
            for entry in entries:
                if entry.path.rstrip("/") == root.rstrip("/"):
                    continue

                if self._is_path_skipped(entry.path):
                    logging.debug("配置跳过路径：%s", entry.path)
                    continue

                if entry.is_dir:
                    if self._should_skip_directory(entry):
                        logging.debug("命中缓存，跳过目录：%s", entry.path)
                        continue

                    resources = self.client.walk([entry.path])
                    episodes = self._collect_episodes(resources, show_path=entry.path)
                    yield (entry.path, entry.lastmod, episodes)
                else:
                    if self._should_skip_directory(entry):
                        logging.debug("命中缓存，跳过文件：%s", entry.path)
                        continue
                    # 根目录下直接存在的文件，视为 show_path 的父目录
                    parent_path = os.path.dirname(entry.path) or "/"
                    episodes = self._collect_episodes([entry], show_path=parent_path)
                    yield (entry.path, entry.lastmod, episodes)

    def _should_skip_directory(self, resource: WebDAVResource) -> bool:
        return self.storage.should_skip_scan(
            path=resource.path,
            remote_lastmod=resource.lastmod,
            cache_ttl_seconds=self._cache_ttl_seconds,
        )

    def _is_path_skipped(self, path: str) -> bool:
        normalized = _normalize_path(path)
        if not normalized:
            return False
        for skip in self.config.skip_paths:
            if normalized == skip:
                return True
            if normalized.startswith(f"{skip}/"):
                return True
        return False

    def _collect_episodes(
        self,
        resources: Iterable[WebDAVResource],
        show_path: Optional[str] = None,
    ) -> List[Episode]:
        episodes: List[Episode] = []
        for item in resources:
            if item.is_dir:
                continue
            if self._is_path_skipped(item.path):
                logging.debug("配置跳过文件：%s", item.path)
                continue
            filename = item.path.split("/")[-1]
            if not self.filter.is_video(filename):
                continue
            lang = self.filter.detect_lang(item.path) or self.filter.detect_lang(filename)
            if lang not in ("美剧", "日剧"):
                continue
            resolved_show_path = show_path or os.path.dirname(item.path) or "/"
            episodes.append(
                Episode(
                    path=item.path,
                    show_path=resolved_show_path,
                    lang=lang,
                    filename=filename,
                    size=item.size,
                    lastmod=item.lastmod,
                    etag=item.etag,
                )
            )
        return episodes

