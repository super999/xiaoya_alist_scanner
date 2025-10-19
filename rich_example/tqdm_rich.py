# pip install rich
import logging
import random
import time
from collections import deque
from threading import Thread, Event

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn,
    TaskProgressColumn
)
from rich.text import Text

console = Console()
log_buffer = deque(maxlen=200)
log_dirty = Event()  # >>> 新增：有新日志时置位

class BufferHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        log_buffer.append(msg)
        log_dirty.set()  # >>> 新增：触发右栏刷新

logger = logging.getLogger("crawler")
logger.setLevel(logging.INFO)
handler = BufferHandler()
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
logger.addHandler(handler)

progress = Progress(
    SpinnerColumn(),
    TextColumn("[bold]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    expand=True,
)

layout = Layout()
layout.split_row(
    Layout(name="left", ratio=1),
    Layout(name="right", ratio=1),
)

def render_logs():
    lines = [Text(l) for l in list(log_buffer)]
    return Panel(Group(*lines[-30:]), title="日志（最近30行）", border_style="cyan")

def crawl_task(item_id, parent_task):
    task_id = progress.add_task(f"抓取项 {item_id}", total=1)
    try:
        t = random.uniform(0.3, 1.2)
        time.sleep(t)
        if random.random() < 0.1:
            raise RuntimeError(f"抓取 {item_id} 失败：网络错误")
        logger.info(f"抓取成功：item={item_id}，耗时 {t:.2f}s")
    except Exception as e:
        logger.error(str(e))
    finally:
        progress.advance(task_id)
        progress.advance(parent_task)

def main(total_items=50, workers=8):
    parent = progress.add_task("总体进度", total=total_items)
    threads = []
    for i in range(total_items):
        th = Thread(target=crawl_task, args=(i + 1, parent), daemon=True)
        threads.append(th)
        th.start()
        while sum(t.is_alive() for t in threads) >= workers:
            time.sleep(0.05)
    for t in threads:
        t.join()

# ------- 运行 -------
layout["left"].update(Panel(progress, title="进度"))
layout["right"].update(render_logs())

# 1) 用 screen=True 走备用屏；2) 让 Progress 自己刷新；3) 右栏按需刷新
with Live(layout, refresh_per_second=12, console=console, screen=True):  # <<< 改成 screen=True
    with progress:
        # 在主线程里跑任务，同时监听日志“脏位”事件，按需更新右栏
        from threading import Thread as _Thread
        runner = _Thread(target=main, kwargs=dict(total_items=80, workers=10), daemon=True)
        runner.start()

        last_len = 0
        while runner.is_alive():
            # 等待“有新日志”或超时，避免忙等
            log_dirty.wait(timeout=0.2)
            if log_dirty.is_set() or len(log_buffer) != last_len:
                last_len = len(log_buffer)
                layout["right"].update(render_logs())
                log_dirty.clear()
            # Progress 自行驱动左栏刷新，无需手动刷新 layout

        runner.join()
        # 收尾：再刷一次日志面板
        layout["right"].update(render_logs())
