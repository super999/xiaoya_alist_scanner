from tqdm import tqdm
import logging
import time

class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            # 不打断进度条
            from tqdm import tqdm as _tqdm
            _tqdm.write(msg)
        except Exception:
            pass

logger = logging.getLogger("crawler")
logger.setLevel(logging.INFO)
h = TqdmLoggingHandler()
h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
logger.addHandler(h)

for i in tqdm(range(100), desc="爬取中"):
    time.sleep(0.05)
    if i % 17 == 0:
        logger.info(f"处理到 {i}")
