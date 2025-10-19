"""剧集扫描主逻辑。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterable, List

from .config import Config
from .filters import EpisodeFilter
from .models import Episode, WebDAVResource
from .state import StateStore
from .webdav import WebDAVClient


@dataclass
class EpisodeScanner:
    """负责 orchestrate WebDAV 扫描流程。"""

    config: Config
    client: WebDAVClient
    state: StateStore
    filter: EpisodeFilter

    def scan(self) -> List[Episode]:
        logging.info("开始扫描 WebDAV（小雅 Alist）...")
        # WebDAV 遍历交给客户端，返回粗粒度的资源列表
        resources = self.client.walk(self.config.roots)
        return self._collect_episodes(resources)

    def _collect_episodes(self, resources: Iterable[WebDAVResource]) -> List[Episode]:
        episodes: List[Episode] = []
        for item in resources:
            if item.is_dir:
                continue
            filename = item.path.split("/")[-1]
            if not self.filter.is_video(filename):
                continue
            lang = self.filter.detect_lang(item.path) or self.filter.detect_lang(filename)
            if lang not in ("美剧", "日剧"):
                continue
            # 统一组装为 Episode 模型，便于后续序列化与状态管理
            episodes.append(
                Episode(
                    path=item.path,
                    lang=lang,
                    filename=filename,
                    size=item.size,
                    lastmod=item.lastmod,
                    etag=item.etag,
                )
            )
        return episodes

    def detect_new(self, episodes: Iterable[Episode]) -> List[Episode]:
        # 仅返回新增的剧集文件列表
        results: List[Episode] = []
        state_data = self.state.load()
        if not state_data:
            logging.info("首次运行：为了避免把历史内容都当作新增，本次不输出新增清单。")
            return []
        for episode in episodes:
            is_new = self.state.detect_new(episode)
            if is_new:
                episode.is_new = True
                results.append(episode)
        return results

    def update_state(self, episodes: Iterable[Episode]) -> None:
        episodes_list = list(episodes)
        for episode in episodes_list:
            self.state.mark_seen(episode)
        self.state.save()
        logging.info(
            "扫描完成，共匹配 %s 个文件。状态已保存到 %s。",
            len(episodes_list),
            self.config.state_file,
        )

    def run(self) -> None:
        episodes = self.scan()
        if self.config.only_new:
            new_items = self.detect_new(episodes)
            payload = [episode.to_dict() for episode in new_items]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            payload = [episode.to_dict() for episode in episodes]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        self.update_state(episodes)
