"""Smoke-тест заполнения комнаты ботами и командного лимита 5v5."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from server import Room  # noqa: E402


class FakeClient:
    def __init__(self, player_id, team, name, hero_id):
        self.player_id = player_id
        self.team = team
        self.name = name
        self.hero_id = hero_id
        self.ready = True
        self.messages = []

    def push(self, msg):
        self.messages.append(msg)


def main() -> int:
    data = loader.load_all()
    room = Room(data, max_players=10)
    room.host_id = "p1"
    room.clients = {
        "p1": FakeClient("p1", "A", "Alpha", "knight"),
        "p2": FakeClient("p2", "B", "Bravo", "archer"),
    }
    room.start_loop = lambda: None
    room.start_match("p1", fill_bots=True, training=False)
    assert room.started
    assert room.world is not None
    assert len(room.world.players) == 10, len(room.world.players)
    assert room.bot_manager is not None
    assert sum(1 for p in room.world.players.values() if p.team == "A") == 5
    assert sum(1 for p in room.world.players.values() if p.team == "B") == 5
    print("OK: room filled to 5v5 with bots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
