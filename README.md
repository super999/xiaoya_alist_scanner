# xiaoya_alist_scanner

小雅网盘（Alist）WebDAV 剧集扫描机器人，现已重构为模块化的面向对象实现，便于复用和扩展。

## 快速开始

```powershell
# Windows PowerShell 示例
$env:WEBDAV_BASE = "http://192.168.9.1:5344/dav"
$env:WEBDAV_USER = "super999"
$env:WEBDAV_PASS = "chenxiawen"
$env:WEBDAV_ROOTS = '["/每日更新/电视剧/日剧", "/每日更新/电视剧/美剧"]'

python scan_webdav_new_episodes.py
```

默认会在仓库根目录生成 / 更新 `state.json`，用来记录已扫描过的剧集文件，避免重复通知。

## 项目结构

- `scan_webdav_new_episodes.py`：保持向后兼容的脚本入口，内部直接调用新的包。  
- `alist_scaner/`：核心实现所在的 Python 包。
	- `config.py`：环境变量驱动的配置读取逻辑。
	- `webdav.py`：WebDAV 客户端封装，包含容错的 PROPFIND 调用。
	- `filters.py`：视频后缀和语言规则的筛选器。
	- `state.py`：状态持久化，使用原子写避免文件损坏。
	- `scanner.py`：剧集扫描主流程，负责整合各模块。
	- `cli.py`：命令行入口与依赖装配函数。

## 环境变量速查

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `WEBDAV_BASE` | WebDAV 基地址（无尾斜杠） | `http://192.168.9.1:5344/dav` |
| `WEBDAV_USER` / `WEBDAV_PASS` | 访问凭证 | `super999` / `chenxiawen` |
| `WEBDAV_ROOTS` | 需要扫描的根目录（JSON 列表字符串） | `['/每日更新/电视剧/日剧', '/每日更新/电视剧/美剧']` |
| `WEBDAV_VERIFY_SSL` | 是否校验证书 | `false` |
| `WEBDAV_STATE_FILE` | 状态文件路径 | `./state.json` |
| `WEBDAV_TIMEOUT` | 请求超时时间（秒） | `20` |
| `WEBDAV_ONLY_NEW` | 是否仅输出“新增”文件 | `true` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

> 所有默认值在运行时会自动写入环境变量，确保与旧脚本保持一致的体验。

## 以包方式调用

```python
from alist_scaner.cli import build_scanner

scanner = build_scanner()
scanner.run()
```

欢迎基于新的包结构继续扩展，例如接入通知机器人、增加更多语言或分类规则等。
