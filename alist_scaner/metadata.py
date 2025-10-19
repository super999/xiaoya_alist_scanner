"""第三方剧集元数据抓取模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from .models import ShowMetadata


def derive_title_from_path(show_path: str) -> str:
    """根据剧集目录路径推导剧名。"""

    if not show_path:
        return ""
    normalized = show_path.rstrip("/")
    if not normalized:
        return ""
    return normalized.split("/")[-1]


@dataclass
class ShowMetadataFetcher:
    """基于 TMDB API 的剧集元数据抓取器。"""

    api_key: str
    session: Optional[requests.Session] = None

    _TMDB_BASE: str = "https://api.themoviedb.org/3"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("TMDB API key is required for metadata fetching")
        if self.session is None:
            self.session = requests.Session()

    def fetch(self, title: str, lang: str) -> Optional[ShowMetadata]:
        """根据剧名和语言抓取评分、简介与类型信息。"""

        if not title:
            return None

        for language_code in self._language_candidates(lang):
            try:
                search_payload = self._request(
                    "search/tv",
                    params={
                        "query": title,
                        "language": language_code,
                        "page": 1,
                        "include_adult": "false",
                    },
                )
            except requests.RequestException as exc:
                logging.warning("请求 TMDB Search TV 失败：%s", exc)
                return None

            results = search_payload.get("results") or []
            if not results:
                continue

            best_match = results[0]
            tv_id = best_match.get("id")
            if not tv_id:
                continue

            try:
                detail_payload = self._request(
                    f"tv/{tv_id}",
                    params={
                        "language": language_code,
                    },
                )
            except requests.RequestException as exc:
                logging.warning("请求 TMDB TV Detail 失败：%s", exc)
                return None

            genres = [
                genre.get("name")
                for genre in detail_payload.get("genres", [])
                if isinstance(genre, dict) and genre.get("name")
            ]
            metadata = ShowMetadata(
                show_path="",
                title=detail_payload.get("name") or best_match.get("name") or title,
                lang=lang,
                rating=self._extract_rating(detail_payload),
                overview=detail_payload.get("overview") or best_match.get("overview"),
                genres=genres,
                source="tmdb",
            )
            if metadata.overview or metadata.rating is not None or metadata.genres:
                return metadata

        logging.info("TMDB 未找到剧集元数据：%s", title)
        return None

    def _language_candidates(self, lang: str) -> List[str]:
        mapping = {
            "日剧": ["zh-CN", "ja-JP"],
            "美剧": ["zh-CN", "en-US"],
        }
        candidates = mapping.get(lang, ["zh-CN", "en-US"])
        # 去重同时保持顺序
        seen = set()
        ordered: List[str] = []
        for item in candidates:
            if item not in seen:
                ordered.append(item)
                seen.add(item)
        return ordered

    def _request(self, path: str, params: Optional[dict] = None) -> dict:
        query = {"api_key": self.api_key}
        if params:
            query.update(params)
        assert self.session is not None  # appease type checkers
        response = self.session.get(f"{self._TMDB_BASE}/{path}", params=query, timeout=15)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_rating(payload: dict) -> Optional[float]:
        rating = payload.get("vote_average")
        if rating is None:
            return None
        try:
            return float(rating)
        except (TypeError, ValueError):
            return None
