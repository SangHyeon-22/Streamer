"""
자동 재시작 래퍼 - main.py가 크래시나도 5초 후 재시작
1주일 무중단 운영용

사용법: python run_forever.py
"""

import subprocess
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    handlers=[
        logging.FileHandler("logs/crash_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ],
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger("run_forever")

RESTART_DELAY = 5  # 재시작 대기 시간 (초)
MAX_RESTARTS_PER_HOUR = 20  # 시간당 최대 재시작 횟수 (무한 루프 방지)


def main():
    logger.info("=" * 50)
    logger.info("  run_forever.py 시작 - 무중단 운영 모드")
    logger.info("=" * 50)

    restart_times = []

    while True:
        now = time.time()

        # 1시간 이내 재시작 횟수 체크
        restart_times = [t for t in restart_times if now - t < 3600]
        if len(restart_times) >= MAX_RESTARTS_PER_HOUR:
            logger.error(f"1시간 내 {MAX_RESTARTS_PER_HOUR}회 이상 크래시. 5분 대기 후 재시작...")
            time.sleep(300)
            restart_times.clear()
            continue

        logger.info(f"main.py 시작 (총 {len(restart_times) + 1}번째)")
        start_time = time.time()

        try:
            result = subprocess.run(
                [sys.executable, "main.py"],
                check=False
            )
            exit_code = result.returncode
        except Exception as e:
            logger.error(f"subprocess 실행 오류: {e}")
            exit_code = -1

        uptime = time.time() - start_time
        restart_times.append(time.time())

        if exit_code == 0:
            logger.info(f"main.py 정상 종료 (업타임: {uptime:.0f}초)")
        else:
            logger.warning(f"main.py 비정상 종료 (코드: {exit_code}, 업타임: {uptime:.0f}초)")

        logger.info(f"{RESTART_DELAY}초 후 재시작...")
        time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    main()
