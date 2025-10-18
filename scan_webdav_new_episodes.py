# -*- coding: utf-8 -*-
"""
扫描 WebDAV（小雅 Alist）下指定目录，找出“新增的美剧/日剧剧集文件”。

用法：
  python scan_webdav_new_episodes.py
配置见文件顶部 CONFIG 段，或用环境变量覆盖。

特性：
- 递归 PROPFIND（Depth: 1 + 队列遍历）
- 通过目录名/文件名规则判断“美剧/日剧”
- 记忆已见文件（state.json），仅输出新出现的文件
- 视频扩展、语言判断规则可配置
"""

import os
import re
import json
import time
import logging
import urllib.parse
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import requests
from requests import HTTPError


if not os.getenv("WEBDAV_USER"):
    # 设置环境变量
    os.environ["WEBDAV_USER"] = "super999"

if not os.getenv("WEBDAV_PASS"):
    os.environ["WEBDAV_PASS"] = "chenxiawen"

if not os.getenv("WEBDAV_BASE"):
    os.environ["WEBDAV_BASE"] = "http://192.168.9.1:5344/dav"

if not os.getenv("WEBDAV_ROOTS"):
    os.environ["WEBDAV_ROOTS"] = '["/每日更新/电视剧/日剧", "/每日更新/电视剧/美剧"]'

if not os.getenv("WEBDAV_VERIFY_SSL"):
    os.environ["WEBDAV_VERIFY_SSL"] = "false"

# =========================
# ======== CONFIG =========
# =========================
CONFIG = {
    # WebDAV 基地址（无尾斜杠）；示例："http://192.168.1.1:5244/dav" 或 "http://router.lan:5244/dav"
    "WEBDAV_BASE": os.getenv("WEBDAV_BASE", "http://127.0.0.1:5244/dav"),

    # 账号与密码（若匿名访问可留空）
    "USERNAME": os.getenv("WEBDAV_USER", ""),
    "PASSWORD": os.getenv("WEBDAV_PASS", ""),

    # 要扫描的根目录（WebDAV 路径，必须以 "/" 开头），可配多条
    "ROOTS": json.loads(os.getenv("WEBDAV_ROOTS", '["/电视剧/美剧", "/电视剧/日剧"]')),

    # 校验证书（https 时），自签名可设为 False
    "VERIFY_SSL": os.getenv("WEBDAV_VERIFY_SSL", "true").lower() == "true",

    # 识别为“剧集文件”的扩展名（小写）
    "VIDEO_EXTS": [".mp4", ".mkv", ".avi", ".mov", ".ts", ".m4v", ".wmv", ".webm"],

    # 用于识别美剧/日剧的规则（命中任一即视为匹配）
    # - 会在完整路径 & 文件名上做不区分大小写匹配
    "LANG_RULES": {
        "美剧": [
            r"美剧", r"\bUS\b", r"\bUSA\b", r"\bEN\b", r"\bEng\b",  # 目录标签
            r"\bS\d{1,2}E\d{1,2}\b",  # SxxExx 通常也可能是欧美剧集
        ],
        "日剧": [
            r"日剧", r"\bJP\b", r"\bJPN\b", r"日本", r"日語|日语|JAP",  # 目录标签
        ]
    },

    # 是否只列出“新增”文件；若为 False 则每次均列出匹配到的所有文件
    "ONLY_NEW": True,

    # 状态文件（记录已见文件），可放到固定路径
    "STATE_FILE": os.getenv("WEBDAV_STATE_FILE", "./state.json"),

    # 超时时间（秒）
    "TIMEOUT": 20,

    # 日志等级：DEBUG/INFO/WARNING/ERROR
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}

logging.basicConfig(
    level=getattr(logging, CONFIG["LOG_LEVEL"].upper(), logging.INFO),
    format="[%(asctime)s] %(levelname)s: %(message)s"
)

NAMESPACES = {
    "d": "DAV:"
}

def _auth_tuple() -> Optional[Tuple[str, str]]:
    user, pwd = CONFIG["USERNAME"], CONFIG["PASSWORD"]
    return (user, pwd) if user or pwd else None

def _join_url(base: str, path: str) -> str:
    # WebDAV 路径一般需要逐段 urlencode（保留 "/"）
    if not path.startswith("/"):
        path = "/" + path
    return base + urllib.parse.quote(path, safe='/%')

def _propfind_smart(url: str, depth: int = 1) -> requests.Response:
    """
    更稳健的 PROPFIND：
    - 原样请求
    - 404 时切换尾斜杠再试一次
    - 仍失败则 Depth:0 再试（有些服务对子目录只接受 0）
    """
    def _do(url_try, d):
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
        resp = requests.request(
            method="PROPFIND",
            url=url_try,
            data=body.encode("utf-8"),
            headers=headers,
            auth=_auth_tuple(),
            verify=CONFIG["VERIFY_SSL"],
            timeout=CONFIG["TIMEOUT"],
        )
        resp.raise_for_status()
        return resp

    # 1) 原样
    try:
        return _do(url, depth)
    except HTTPError as e1:
        status = getattr(e1.response, "status_code", None)
        # 2) 404 ↔️ 尾斜杠切换
        if status == 404:
            if url.endswith("/"):
                alt = url[:-1]
            else:
                alt = url + "/"
            try:
                return _do(alt, depth)
            except HTTPError as e2:
                # 3) 再退一步：Depth:0
                try:
                    return _do(alt, 0)
                except Exception:
                    # 全部失败再抛原错误，但把两个尝试的 URL 都记录出来
                    raise HTTPError(
                        f"PROPFIND 404. Tried: {url}  and  {alt} (Depth {depth} / then 0)"
                    ) from e2
        # 其他状态码原样抛
        raise

def _propfind(url: str, depth: int = 1) -> requests.Response:
    headers = {
        "Depth": str(depth),
        "Content-Type": "text/xml; charset=utf-8",
    }
    # 要求的最小 prop（href / getcontentlength / resourcetype / getlastmodified / getetag）
    body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:resourcetype/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:getetag/>
  </d:prop>
</d:propfind>"""

    resp = requests.request(
        method="PROPFIND",
        url=url,
        data=body.encode("utf-8"),
        headers=headers,
        auth=_auth_tuple(),
        verify=CONFIG["VERIFY_SSL"],
        timeout=CONFIG["TIMEOUT"],
    )
    resp.raise_for_status()
    return resp

def _parse_propfind_xml(xml_text: str) -> List[Dict]:
    """
    解析 PROPFIND 响应，返回条目列表：
    [{href, is_dir, size, lastmod, etag}]
    """
    out = []
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
        size = int(size_el.text) if (size_el is not None and size_el.text and size_el.text.isdigit()) else 0

        lastmod_el = propstat.find("d:getlastmodified", NAMESPACES)
        lastmod = (lastmod_el.text or "") if lastmod_el is not None else ""

        etag_el = propstat.find("d:getetag", NAMESPACES)
        etag = (etag_el.text or "") if etag_el is not None else ""

        out.append({
            "href": href,
            "is_dir": is_dir,
            "size": size,
            "lastmod": lastmod,
            "etag": etag,
        })
    return out

def _href_to_path(href: str, base: str) -> str:
    """
    把绝对 href 转换为 WebDAV 下的“路径”（以 / 开头，未解码）
    示例：
      base = http://router/dav
      href  = /dav/电视剧/美剧/Show/xxx.mkv
      -> /电视剧/美剧/Show/xxx.mkv
    """
    # 注意：有的服务返回的是绝对路径，有的是完整 URL，这里都兼容
    # 1) 如果是完整 URL，先取 path
    parsed = urllib.parse.urlparse(href)
    path = parsed.path or href

    base_path = urllib.parse.urlparse(base).path  # 例如 /dav
    if base_path and path.startswith(base_path):
        path = path[len(base_path):]
        if not path.startswith("/"):
            path = "/" + path
    # 新增：把 %E6%... 解码成中文，内部统一使用“解码后”的路径
    path = unquote(path)
    return path

def load_state() -> Dict[str, Dict]:
    if not os.path.exists(CONFIG["STATE_FILE"]):
        return {}
    with open(CONFIG["STATE_FILE"], "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_state(state: Dict[str, Dict]) -> None:
    tmp = CONFIG["STATE_FILE"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG["STATE_FILE"])

def is_video_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in CONFIG["VIDEO_EXTS"])

def match_lang(path_or_name: str) -> Optional[str]:
    s = path_or_name.lower()
    for lang, patterns in CONFIG["LANG_RULES"].items():
        for p in patterns:
            if re.search(p, path_or_name, flags=re.IGNORECASE):
                return lang
    return None

def list_recursive(root_path: str) -> List[Dict]:
    """
    从 root_path 递归列出所有子项（文件/目录）。
    返回字典列表：{path, is_dir, size, lastmod, etag}
    """
    base = CONFIG["WEBDAV_BASE"]
    results = []

    # BFS 队列
    queue = [root_path]
    seen_dirs = set()

    while queue:
        cur = queue.pop(0)
        cur_url = _join_url(base, cur)
        logging.debug(f"PROPFIND {urllib.parse.unquote(cur_url)}")

        try:
            resp = _propfind_smart(cur_url, depth=1)
        except Exception as e:
            logging.warning(f"PROPFIND 失败：{urllib.parse.unquote(cur_url)} -> {e}")
            continue

        entries = _parse_propfind_xml(resp.text)
        for it in entries:
            # WebDAV 会把当前目录本身也列出来，需跳过
            p = _href_to_path(it["href"], base)
            if p.rstrip("/") == cur.rstrip("/"):
                continue

            rec = {
                "path": p,
                "is_dir": it["is_dir"],
                "size": it["size"],
                "lastmod": it["lastmod"],
                "etag": it["etag"],
            }
            results.append(rec)

            if it["is_dir"]:
                if p not in seen_dirs:
                    seen_dirs.add(p)
                    queue.append(p)
    return results

def scan_roots_and_collect() -> List[Dict]:
    """
    扫描多个 ROOTS，返回满足“美剧/日剧 + 视频扩展”的文件清单
    每项：{path, lang, filename, size, lastmod, etag}
    """
    all_files = []
    for root in CONFIG["ROOTS"]:
        root = root if root.startswith("/") else "/" + root
        logging.info(f"扫描根目录：{root}")
        items = list_recursive(root)
        for it in items:
            if it["is_dir"]:
                continue
            filename = it["path"].split("/")[-1]
            if not is_video_file(filename):
                continue
            # 语言识别：在“完整路径 + 文件名”上做匹配
            lang = match_lang(it["path"]) or match_lang(filename)
            if lang not in ("美剧", "日剧"):
                # 如果你的目录结构已经严格区分（例如 ROOT 就是 /电视剧/美剧），也可以直接用 root 名称作为 lang
                # 例如：
                # lang = "美剧" if "美剧" in root else "日剧"
                # 这里保留自动识别，减少误报
                continue

            all_files.append({
                "path": it["path"],
                "lang": lang,
                "filename": filename,
                "size": it["size"],
                "lastmod": it["lastmod"],
                "etag": it["etag"],
            })
    return all_files

def detect_new_items(current: List[Dict], state: Dict[str, Dict]) -> List[Dict]:
    """
    与 state 对比，找出“新增”的条目。
    采用 path 做主键；若首次运行，默认不把全部当作新增（可按需调整）。
    """
    new_items = []
    for rec in current:
        key = rec["path"]
        if key not in state:
            # 新出现
            new_items.append(rec)
    return new_items

def update_state(state: Dict[str, Dict], current: List[Dict]) -> Dict[str, Dict]:
    for rec in current:
        key = rec["path"]
        state[key] = {
            "size": rec["size"],
            "etag": rec["etag"],
            "lastmod": rec["lastmod"],
            "lang": rec["lang"],
            "filename": rec["filename"],
            "ts_seen": int(time.time()),
        }
    return state

def main():
    logging.info("开始扫描 WebDAV（小雅 Alist）...")
    state = load_state()
    files = scan_roots_and_collect()

    if CONFIG["ONLY_NEW"]:
        new_items = detect_new_items(files, state)
        if not state:
            logging.info("首次运行：为了避免把历史内容都当作新增，本次不输出新增清单。")
            new_items = []
        # 输出结果
        print(json.dumps(new_items, ensure_ascii=False, indent=2))
    else:
        # 输出所有匹配文件
        print(json.dumps(files, ensure_ascii=False, indent=2))

    # 更新状态并保存
    new_state = update_state(state, files)
    save_state(new_state)
    logging.info(f"扫描完成，共匹配 {len(files)} 个文件。状态已保存到 {CONFIG['STATE_FILE']}。")

if __name__ == "__main__":
    main()
