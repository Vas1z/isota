"""Smoke-тест LAN-протокола: сервер + два клиента, без pygame.

Запуск из корня проекта:
    python tests/net_smoke.py
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from netclient import NetClient  # noqa: E402


def wait_port(host: str, port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def collect(client: NetClient, seconds: float) -> list:
    messages = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        messages.extend(client.poll())
        time.sleep(0.01)
    return messages


def wait_for(client: NetClient, mtype: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    pending = []
    while time.time() < deadline:
        for msg in client.poll():
            if msg.get("type") == mtype:
                return msg
            pending.append(msg)
        time.sleep(0.01)
    raise AssertionError(f"no {mtype} from server, got {pending[:5]}")


def main() -> int:
    host = "127.0.0.1"
    port = 8771

    server = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py"), "--host", host, "--port", str(port)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    a = b = None
    try:
        if not wait_port(host, port):
            raise AssertionError("server did not open port")

        a = NetClient(host, port, "Alpha")
        welcome_a = wait_for(a, "welcome")
        b = NetClient(host, port, "Bravo")
        welcome_b = wait_for(b, "welcome")

        assert welcome_a["player_id"] != welcome_b["player_id"], "same player id"
        assert {welcome_a["team"], welcome_b["team"]} == {"A", "B"}, "teams are not A/B"

        # Двигаем героев в разные стороны.
        a.send_command(1, {"type": "move", "x": 6.0, "y": 18.0})
        b.send_command(1, {"type": "move", "x": 18.0, "y": 6.0})

        messages = collect(a, 2.5)
        snaps = [m["data"] for m in messages if m.get("type") == "snap"]
        assert snaps, "no snapshots received"

        latest = snaps[-1]
        assert len(latest.get("players", {})) == 2, "expected 2 players"
        assert len(latest.get("units", [])) >= 10, "expected towers and heroes"

        hero_a = latest["players"][welcome_a["player_id"]]["hero"]
        hero_b = latest["players"][welcome_b["player_id"]]["hero"]
        unit_a = next(u for u in latest["units"] if u["id"] == hero_a)
        unit_b = next(u for u in latest["units"] if u["id"] == hero_b)

        assert unit_a["y"] < 20.0 - 0.3, f"hero A did not move: {unit_a}"
        assert unit_b["x"] < 20.0 - 0.3, f"hero B did not move: {unit_b}"

        print("OK: two clients connected")
        print("  player A:", welcome_a["player_id"], welcome_a["team"], "->", (unit_a["x"], unit_a["y"]))
        print("  player B:", welcome_b["player_id"], welcome_b["team"], "->", (unit_b["x"], unit_b["y"]))
        print("  snapshots:", len(snaps), "units in latest:", len(latest["units"]))
        return 0
    finally:
        for client in (a, b):
            if client is not None:
                client.close()
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        output = server.stdout.read() if server.stdout else ""
        if output and any(word in output for word in ("ERROR", "Traceback")):
            print("--- server log ---")
            print(output)


if __name__ == "__main__":
    raise SystemExit(main())
