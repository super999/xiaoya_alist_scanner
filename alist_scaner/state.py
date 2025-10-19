"""状态存储模块。"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict

from .models import Episode


@dataclass
class StateStore:
    """管理 state.json 的读写。"""

    path: str
    _cache: Dict[str, Dict] = field(default_factory=dict, init=False)

    def load(self) -> Dict[str, Dict]:
        if self._cache:
            return self._cache
        if not os.path.exists(self.path):
            self._cache = {}
            return self._cache
        with open(self.path, "r", encoding="utf-8") as fp:
            try:
                self._cache = json.load(fp)
            except Exception:
                self._cache = {}
        return self._cache

    def save(self) -> None:
        # 写入时采用临时文件 + 原子替换，避免扫描过程中意外中断导致文件损坏
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(self._cache, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def mark_seen(self, episode: Episode) -> None:
        state = self.load()
        state[episode.path] = {
            "size": episode.size,
            "etag": episode.etag,
            "lastmod": episode.lastmod,
            "lang": episode.lang,
            "filename": episode.filename,
            "show_path": episode.show_path,
            "ts_seen": int(time.time()),
        }

    def detect_new(self, episode: Episode) -> bool:
        state = self.load()
        return episode.path not in state
