# xiaoya_alist_scanner

小雅网盘（Alist）WebDAV 剧集扫描机器人，现已重构为模块化的面向对象实现，便于复用和扩展。

## 快速开始

```powershell
# Windows PowerShell 示例
$env:WEBDAV_BASE = "http://192.168.9.1:5344/dav"
$env:WEBDAV_USER = ""
$env:WEBDAV_PASS = ""
$env:WEBDAV_ROOTS = '["/每日更新/电视剧/日剧", "/每日更新/电视剧/美剧"]'

python scan_webdav_new_episodes.py
```

亦可在项目根目录创建 `.env` 文件管理敏感凭证（默认会自动加载，已有环境变量仍可覆盖）：

```
WEBDAV_USER=
WEBDAV_PASS=
```

默认会在仓库根目录生成 / 更新 `state.json`，用来记录已扫描过的剧集文件，避免重复通知。

## 项目结构

- `scan_webdav_new_episodes.py`：保持向后兼容的脚本入口，内部直接调用新的包。  
- `alist_scaner/`：核心实现所在的 Python 包。
	- `config.py`：环境变量驱动的配置读取逻辑。
	- `webdav.py`：WebDAV 客户端封装，包含容错的 PROPFIND 调用。
	- `filters.py`：视频后缀和语言规则的筛选器。
	- `state.py`：状态持久化，使用原子写避免文件损坏。
	- `storage.py`：SQLite 本地数据库，记录剧集及目录缓存信息。
	- `scanner.py`：剧集扫描主流程，负责整合各模块。
	- `cli.py`：命令行入口与依赖装配函数。

## 环境变量速查

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `WEBDAV_BASE` | WebDAV 基地址（无尾斜杠） | `http://192.168.9.1:5344/dav` |
| `WEBDAV_USER` / `WEBDAV_PASS` | 访问凭证 | `aaa` / `bbb` |
| `WEBDAV_ROOTS` | 需要扫描的根目录（JSON 列表字符串） | `['/每日更新/电视剧/日剧', '/每日更新/电视剧/美剧']` |
| `WEBDAV_VERIFY_SSL` | 是否校验证书 | `false` |
| `WEBDAV_STATE_FILE` | 状态文件路径 | `./state.json` |
| `WEBDAV_TIMEOUT` | 请求超时时间（秒） | `20` |
| `WEBDAV_ONLY_NEW` | 是否仅输出“新增”文件 | `true` |
| `WEBDAV_DB_FILE` | SQLite 数据库存储路径 | `./alist_scaner.db` |
| `WEBDAV_SCAN_CACHE_HOURS` | 剧集目录缓存时长（小时），缓存内且未更新则跳过扫描 | `24` |
| `WEBDAV_SKIP_PATHS_FILE` | 存放需跳过目录列表的 JSON 文件路径 | `./skip_paths.json` |
| `WEBDAV_ENV_FILE` | 自定义 `.env` 文件路径 | `.env` |
| `LOG_LEVEL` | 日志级别 | `DEBUG` |

> 所有默认值在运行时会自动写入环境变量，确保与旧脚本保持一致的体验。

## 新增特性

- **本地 SQLite 持久化**：每个剧集在扫描完成后立即落库，方便后续做统计或与其他服务联动。
- **目录级缓存控制**：借助 `WEBDAV_SCAN_CACHE_HOURS` 与 WebDAV 中的最后修改时间，重复扫描会在缓存期内自动跳过，常见场景可大幅降低同目录的重复请求次数。
- **增量扫描**：若目录上次扫描后的最后修改时间发生变化，会立即重新递归该目录，确保新增剧集不会因缓存而错过。

## 跳过特定目录

若希望永久跳过某些 WebDAV 目录（例如 `/每日更新/电视剧/日剧/【已完结】`），可以创建 `skip_paths.json` 文件，内容需是字符串数组：

```json
[
	"/每日更新/电视剧/日剧/【已完结】",
	"/每日更新/电视剧/日剧/测试目录"
]
```

将文件路径写入环境变量 `WEBDAV_SKIP_PATHS_FILE`（默认即为 `./skip_paths.json`）后，扫描器会在遍历时忽略列表中的目录及其子项。

## 以包方式调用

```python
from alist_scaner.cli import build_scanner

scanner = build_scanner()
scanner.run()
```

欢迎基于新的包结构继续扩展，例如接入通知机器人、增加更多语言或分类规则等。
