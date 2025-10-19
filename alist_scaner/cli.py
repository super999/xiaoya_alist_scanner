"""命令行入口。"""

from __future__ import annotations

import logging

from .config import Config
from .filters import EpisodeFilter
from .scanner import EpisodeScanner
from .state import StateStore
from .webdav import WebDAVClient


def build_scanner() -> EpisodeScanner:
    """构建带依赖的扫描器实例，用于脚本或其他调用者复用。"""

    config = Config.from_env()
    client = WebDAVClient(
        base_url=config.webdav_base,
        auth=(config.username, config.password) if (config.username or config.password) else None,
        verify_ssl=config.verify_ssl,
        timeout=config.timeout,
    )
    state = StateStore(config.state_file)
    episode_filter = EpisodeFilter(config.video_exts, config.lang_rules)

    # 维持同旧脚本的日志格式
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    return EpisodeScanner(
        config=config,
        client=client,
        state=state,
        filter=episode_filter,
    )


def main() -> None:
    """命令行执行入口。"""

    scanner = build_scanner()
    scanner.run()


if __name__ == "__main__":
    main()
