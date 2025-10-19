# -*- coding: utf-8 -*-
"""WebDAV 剧集扫描脚本入口。

本文件保留为兼容旧调用方式，内部已重构为面向对象模块。
真正的实现位于 :mod:`alist_scaner` 包内，可直接复用其中的类。
"""

from __future__ import annotations

from alist_scaner.cli import main


if __name__ == "__main__":
    main()
