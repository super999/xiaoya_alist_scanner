"""筛选与匹配逻辑。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass
class EpisodeFilter:
    """负责判断文件是否为目标剧集。"""

    video_exts: Iterable[str]
    lang_rules: Dict[str, Iterable[str]]

    def is_video(self, filename: str) -> bool:
        # 仅根据扩展名识别视频文件，保持逻辑简单明了
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in self.video_exts)

    def detect_lang(self, path_or_name: str) -> Optional[str]:
        # 允许在完整路径或文件名中命中语言关键字
        for lang, patterns in self.lang_rules.items():
            for pattern in patterns:
                if re.search(pattern, path_or_name, flags=re.IGNORECASE):
                    return lang
        return None
