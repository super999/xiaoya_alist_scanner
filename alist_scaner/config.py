"""配置加载模块。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List


def _normalize_path(path: str) -> str:
    path = path.strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() == "true"


@dataclass
class Config:
    """应用运行所需的配置参数。"""

    webdav_base: str
    username: str
    password: str
    roots: List[str]
    verify_ssl: bool
    video_exts: List[str]
    lang_rules: Dict[str, List[str]]
    only_new: bool  # 是否仅处理新增文件
    state_file: str
    timeout: int
    log_level: str
    database_file: str
    scan_cache_hours: int
    skip_paths_file: str
    skip_paths: List[str]
    env_file: str
    tmdb_api_key: str
    metadata_cache_hours: int
    raw_environment: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Config":
        """根据环境变量读取配置。"""

        env_file = os.getenv("WEBDAV_ENV_FILE", ".env")
        cls._load_dotenv(env_file)

        # 默认值同旧脚本保持一致
        # 这些默认值直接复用旧脚本里硬编码的值，便于保持行为一致
        defaults = {
            "WEBDAV_BASE": "http://192.168.9.1:5344/dav",
            "WEBDAV_USER": "",
            "WEBDAV_PASS": "",
            "WEBDAV_ROOTS": '["/每日更新/电视剧/日剧", "/每日更新/电视剧/美剧"]',
            "WEBDAV_VERIFY_SSL": "false",
            "WEBDAV_STATE_FILE": "./state.json",
            "LOG_LEVEL": "DEBUG",
            "WEBDAV_TIMEOUT": "20",
            "WEBDAV_ONLY_NEW": "true",
            "WEBDAV_DB_FILE": "./alist_scaner.db",
            "WEBDAV_SCAN_CACHE_HOURS": "24",
            "WEBDAV_SKIP_PATHS_FILE": "./skip_paths.json",
            "WEBDAV_ENV_FILE": env_file,
            "TMDB_API_KEY": "",
            "METADATA_CACHE_HOURS": "0",
        }

        # 兼容旧脚本——缺省时直接把默认值写入环境变量，方便外部复用
        for key, value in defaults.items():
            os.environ.setdefault(key, value)

        env_snapshot = {key: os.getenv(key, defaults.get(key, "")) for key in defaults}

        # ROOTS 依旧采用 JSON 字符串配置，兼容原脚本的环境变量写法
        try:
            roots = json.loads(os.getenv("WEBDAV_ROOTS", defaults["WEBDAV_ROOTS"]))
        except json.JSONDecodeError as exc:
            raise ValueError("WEBDAV_ROOTS 必须为 JSON 列表字符串") from exc

        if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
            raise ValueError("WEBDAV_ROOTS 需要是字符串数组，例如 ['美剧路径', '日剧路径']")

        only_new_env = os.getenv("WEBDAV_ONLY_NEW", defaults["WEBDAV_ONLY_NEW"])
        try:
            timeout = int(os.getenv("WEBDAV_TIMEOUT", defaults["WEBDAV_TIMEOUT"]))
        except ValueError as exc:
            raise ValueError("WEBDAV_TIMEOUT 必须是整数秒数") from exc
        try:
            scan_cache_hours = int(
                os.getenv("WEBDAV_SCAN_CACHE_HOURS", defaults["WEBDAV_SCAN_CACHE_HOURS"])
            )
        except ValueError as exc:
            raise ValueError("WEBDAV_SCAN_CACHE_HOURS 必须是整数小时") from exc

        try:
            metadata_cache_hours = int(
                os.getenv("METADATA_CACHE_HOURS", defaults["METADATA_CACHE_HOURS"])
            )
        except ValueError as exc:
            raise ValueError("METADATA_CACHE_HOURS 必须是整数小时") from exc

        skip_paths_file = os.getenv(
            "WEBDAV_SKIP_PATHS_FILE", defaults["WEBDAV_SKIP_PATHS_FILE"]
        )
        skip_paths: List[str] = []
        if skip_paths_file:
            try:
                skip_paths = cls._load_skip_paths(skip_paths_file)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"跳过目录配置文件 {skip_paths_file} 不是合法的 JSON 列表"
                ) from exc
            except OSError as exc:
                raise OSError(f"无法读取跳过目录配置文件 {skip_paths_file}: {exc}") from exc

        config = cls(
            webdav_base=os.getenv("WEBDAV_BASE", defaults["WEBDAV_BASE"]),
            username=os.getenv("WEBDAV_USER", defaults["WEBDAV_USER"]),
            password=os.getenv("WEBDAV_PASS", defaults["WEBDAV_PASS"]),
            roots=[root if root.startswith("/") else f"/{root}" for root in roots],
            verify_ssl=_env_bool("WEBDAV_VERIFY_SSL", defaults["WEBDAV_VERIFY_SSL"].lower() == "true"),
            video_exts=[".mp4", ".mkv", ".avi", ".mov", ".ts", ".m4v", ".wmv", ".webm"],
            lang_rules={
                "美剧": [
                    r"美剧",
                    r"\bUS\b",
                    r"\bUSA\b",
                    r"\bEN\b",
                    r"\bEng\b",
                    r"\bS\d{1,2}E\d{1,2}\b",
                ],
                "日剧": [
                    r"日剧",
                    r"\bJP\b",
                    r"\bJPN\b",
                    r"日本",
                    r"日語|日语|JAP",
                ],
            },
            only_new=only_new_env.lower() != "false",
            state_file=os.getenv("WEBDAV_STATE_FILE", defaults["WEBDAV_STATE_FILE"]),
            timeout=timeout,
            log_level=os.getenv("LOG_LEVEL", defaults["LOG_LEVEL"]),
            database_file=os.getenv("WEBDAV_DB_FILE", defaults["WEBDAV_DB_FILE"]),
            scan_cache_hours=scan_cache_hours,
            skip_paths_file=skip_paths_file,
            skip_paths=skip_paths,
            env_file=env_file,
            tmdb_api_key=os.getenv("TMDB_API_KEY", defaults["TMDB_API_KEY"]),
            metadata_cache_hours=metadata_cache_hours,
            raw_environment=env_snapshot,
        )

        # 在此初始化基础日志配置，方便 CLI 或其他入口复用
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="[%(asctime)s] %(levelname)s: %(message)s",
        )

        return config

    @staticmethod
    def _load_skip_paths(file_path: str) -> List[str]:
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise ValueError("跳过目录配置文件需要是字符串列表 JSON，例如 ['路径1', '路径2']")
        normalized: List[str] = []
        for item in data:
            normalized_path = _normalize_path(item)
            if not normalized_path:
                continue
            normalized.append(normalized_path)
        return normalized

    @staticmethod
    def _load_dotenv(file_path: str) -> None:
        if not file_path or not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                for line in fp:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if "=" not in stripped:
                        continue
                    key, value = stripped.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if not key:
                        continue
                    # 若环境变量已存在，优先保留外部传入的值
                    os.environ.setdefault(key, value)
        except OSError:
            # 静默忽略读取失败，后续会沿用默认值
            return
