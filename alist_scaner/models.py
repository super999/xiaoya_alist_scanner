"""领域模型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class WebDAVResource:
    """表示一次 PROPFIND 返回的资源。"""

    path: str
    is_dir: bool
    size: int
    lastmod: str
    etag: str


@dataclass
class Episode:
    """匹配到的剧集文件。"""

    path: str
    lang: str
    filename: str
    size: int
    lastmod: str
    etag: str
    is_new: Optional[bool] = None

    def to_dict(self, include_is_new: bool = False) -> dict:
        """转为便于序列化的字典。"""

        data = {
            "path": self.path,
            "lang": self.lang,
            "filename": self.filename,
            "size": self.size,
            "lastmod": self.lastmod,
            "etag": self.etag,
        }
        if include_is_new and self.is_new is not None:
            # 仅在需要时附加 is_new 字段，保持对外兼容
            data["is_new"] = self.is_new
        return data
