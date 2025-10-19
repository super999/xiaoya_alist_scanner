"""WebDAV 客户端封装。"""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
from urllib.parse import unquote

import requests
from requests import HTTPError

from .models import WebDAVResource

NAMESPACES = {
    "d": "DAV:",
}


@dataclass
class WebDAVClient:
    """负责与 WebDAV 服务交互。"""

    base_url: str
    auth: Optional[Tuple[str, str]]
    verify_ssl: bool
    timeout: int

    def join_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + urllib.parse.quote(path, safe="/%")

    def propfind_smart(self, url: str, depth: int = 1) -> requests.Response:
        def _do(url_try: str, d: int) -> requests.Response:
            headers = {
                "Depth": str(d),
                "Content-Type": "text/xml; charset=utf-8",
            }
            body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:resourcetype/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:getetag/>
  </d:prop>
</d:propfind>"""
            response = requests.request(
                method="PROPFIND",
                url=url_try,
                data=body.encode("utf-8"),
                headers=headers,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response

        try:
            return _do(url, depth)
        except HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 404:
                alt = url[:-1] if url.endswith("/") else url + "/"
                try:
                    return _do(alt, depth)
                except HTTPError as exc2:
                    try:
                        return _do(alt, 0)
                    except Exception as exc3:  # noqa: BLE001
                        raise HTTPError(
                            f"PROPFIND 404. Tried: {url} and {alt} (Depth {depth} / then 0)"
                        ) from exc3
            raise

    def list_directory(self, path: str, depth: int = 1) -> List[WebDAVResource]:
        url = self.join_url(path)
        logging.debug("PROPFIND %s", urllib.parse.unquote(url))
        response = self.propfind_smart(url, depth=depth)
        return self._parse_propfind_xml(response.text)

    def walk(self, roots: Iterable[str]) -> List[WebDAVResource]:
        results: List[WebDAVResource] = []
        queue = list(roots)
        seen_dirs = set()

        while queue:
            current = queue.pop(0)
            # 每一层都以 Depth=1 枚举子节点，配合队列实现广度优先遍历
            try:
                entries = self.list_directory(current, depth=1)
                # print(entries)
                for entry in entries:
                    logging.debug("walk -> list_directory -> Found: %s (is_dir=%s)", entry.path, entry.is_dir)
            except Exception as exc:  # noqa: BLE001
                logging.warning("PROPFIND 失败：%s -> %s", urllib.parse.unquote(current), exc)
                continue

            for resource in entries:
                if resource.path.rstrip("/") == current.rstrip("/"):
                    continue
                results.append(resource)
                if resource.is_dir and resource.path not in seen_dirs:
                    seen_dirs.add(resource.path)
                    queue.append(resource.path)
        return results

    def _parse_propfind_xml(self, xml_text: str) -> List[WebDAVResource]:
        resources: List[WebDAVResource] = []
        root = ET.fromstring(xml_text)
        for resp in root.findall("d:response", NAMESPACES):
            href_el = resp.find("d:href", NAMESPACES)
            if href_el is None:
                continue
            href = href_el.text or ""
            propstat = resp.find("d:propstat/d:prop", NAMESPACES)
            if propstat is None:
                continue
            rtype = propstat.find("d:resourcetype", NAMESPACES)
            is_dir = rtype is not None and rtype.find("d:collection", NAMESPACES) is not None
            size_el = propstat.find("d:getcontentlength", NAMESPACES)
            if size_el is not None and size_el.text and size_el.text.isdigit():
                size = int(size_el.text)
            else:
                size = 0
            lastmod_el = propstat.find("d:getlastmodified", NAMESPACES)
            lastmod = (lastmod_el.text or "") if lastmod_el is not None else ""
            etag_el = propstat.find("d:getetag", NAMESPACES)
            etag = (etag_el.text or "") if etag_el is not None else ""
            # PROPFIND 中给出的 href 可能包含完整 URL，这里统一为解码后的 WebDAV 路径
            resources.append(
                WebDAVResource(
                    path=self._href_to_path(href),
                    is_dir=is_dir,
                    size=size,
                    lastmod=lastmod,
                    etag=etag,
                )
            )
        return resources

    def _href_to_path(self, href: str) -> str:
        parsed = urllib.parse.urlparse(href)
        path = parsed.path or href
        base_path = urllib.parse.urlparse(self.base_url).path
        if base_path and path.startswith(base_path):
            path = path[len(base_path):]
            if not path.startswith("/"):
                path = "/" + path
        # 解码百分号编码，便于后续中文路径匹配
        return unquote(path)
