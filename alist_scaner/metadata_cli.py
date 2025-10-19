"""剧集元数据抓取命令行入口。"""

from __future__ import annotations

import logging

from .config import Config
from .metadata import ShowMetadataFetcher
from .metadata_updater import MetadataUpdater
from .storage import SQLiteStore


def build_metadata_updater() -> MetadataUpdater:
    """构建元数据抓取器，便于脚本或其他模块复用。"""

    config = Config.from_env()
    if not config.tmdb_api_key:
        raise RuntimeError("未配置 TMDB_API_KEY，无法抓取剧集元数据。")

    storage = SQLiteStore(config.database_file)
    fetcher = ShowMetadataFetcher(api_key=config.tmdb_api_key)
    return MetadataUpdater(config=config, storage=storage, fetcher=fetcher)


def main() -> None:
    try:
        updater = build_metadata_updater()
    except RuntimeError as exc:
        logging.error("%s", exc)
        return

    updater.run()


if __name__ == "__main__":
    main()
