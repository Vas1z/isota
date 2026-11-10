"""Простой лог активности агентов.

Из другого агента/скрипта:
    python agent_log.py "Subagent-A" "рисую портреты героев"

Или из Python:
    from agent_log import log
    log("Main", "добавляю лобби")
"""

import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "logs" / "agents.log"


def log(agent: str, message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{stamp} | {agent} | {message}\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('usage: python agent_log.py "<agent>" "<message>"')
        raise SystemExit(1)
    log(sys.argv[1], " ".join(sys.argv[2:]))
