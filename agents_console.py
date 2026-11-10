"""Живой просмотр лога агентов в консоли. Без зависимостей.

Запуск:
    python agents_console.py
или двойной клик по agents.bat (откроется отдельное окно).
"""

import os
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "logs" / "agents.log"


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def format_line(line: str) -> str:
    parts = line.rstrip("\n").split(" | ", 2)
    if len(parts) != 3:
        return line.rstrip()
    stamp, agent, message = parts
    palette = {
        "Main": "96",
        "Subagent-A": "93",
        "Subagent-B": "92",
        "Subagent": "93",
    }
    code = palette.get(agent, "95")
    return f"{color(stamp, '90')} {color(agent, code)} {message}"


def main() -> None:
    os.system("")  # включить ANSI-цвета в Windows
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.touch(exist_ok=True)

    print(color("=== isota agents ===", "1;96"))
    print(f"log: {LOG_PATH}")
    print("Ctrl+C — выход\n")

    with LOG_PATH.open("r", encoding="utf-8", errors="replace") as file:
        lines = file.readlines()
        for line in lines[-20:]:
            print(format_line(line), flush=True)
        if not lines:
            print(color("пока пусто, ждём агентов...", "90"), flush=True)
        file.seek(0, os.SEEK_END)

        while True:
            line = file.readline()
            if line:
                print(format_line(line), flush=True)
            else:
                time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
