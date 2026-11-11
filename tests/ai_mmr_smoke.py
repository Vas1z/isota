"""Smoke-тест ботов, MMR-заглушки, предсказания и лаг-компенсации."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.ai import BotManager  # noqa: E402
from shared.mmr import find_match, update_mmr  # noqa: E402
from shared.prediction import LagCompensator, predict_position  # noqa: E402
from shared.protocol import SNAPSHOT_RATE, TICK_RATE  # noqa: E402
from shared.sim import Unit, World  # noqa: E402


def main() -> int:
    data = loader.load_all()
    assert TICK_RATE == 60 and SNAPSHOT_RATE == 30

    # Бот двигается и не падает.
    world = World(data)
    bot_hero = world.add_player("bot1", "A", "Bot", hero_id="knight")
    world.add_player("p2", "B", "Enemy", hero_id="archer")
    manager = BotManager(world, ["bot1"], seed=1)
    start = bot_hero.pos
    for _ in range(240):
        manager.update(1 / 60)
        world.tick(1 / 60)
    assert bot_hero.pos != start, "bot did not move"

    # MMR-заглушка.
    profiles = {}
    before = update_mmr("Alpha", True, profiles)["mmr"]
    after = update_mmr("Alpha", False, profiles)["mmr"]
    assert after < before
    match = find_match(["Alpha", "Bravo"], profiles)
    assert match["ok"] and match["players"] == ["Alpha", "Bravo"]

    # Предсказание движения.
    pos = predict_position((0.0, 0.0), (10.0, 0.0), 2.0, 0.5)
    assert abs(pos[0] - 1.0) < 1e-9 and abs(pos[1]) < 1e-9

    # Лаг-компенсация.
    lag = LagCompensator(max_ticks=4)
    unit = Unit(uid=7, team="A", kind="hero", pos=(1.0, 2.0), hp=10, max_hp=10)
    lag.record(10, [unit])
    unit.pos = (2.0, 2.0)
    lag.record(11, [unit])
    assert lag.position_at(7, 10) == (1.0, 2.0)
    assert lag.position_at(7, 11) == (2.0, 2.0)

    print("OK: bots, MMR stub, prediction, lag compensation, 60/30 rates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
