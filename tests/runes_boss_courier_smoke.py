"""Smoke-тест рун, босса и курьера."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()

    # Руна богатства/мудрости подбирается и уходит на респавн 120 секунд.
    world = World(data)
    hero = world.add_player("p1", "A", hero_id="knight")
    player = world.players["p1"]
    rune = next(r for r in world.runes if r["kind"] == "wealth")
    hero.pos = rune["pos"]
    world.match_time = 0.0
    gold_before = player.gold
    world.tick(1 / 30)
    assert not rune["active"] and rune["timer"] > 0
    assert player.gold > gold_before
    rune["timer"] = 0.01
    world.tick(1 / 30)
    assert rune["active"] and rune["timer"] == 0.0

    # Босс: вторая фаза, дроп баффа, респавн 8-11 минут.
    world_b = World(data)
    hero_b = world_b.add_player("p1", "A")
    world_b.match_time = 0.0
    assert world_b.boss is not None
    world_b.boss.hp = world_b.boss.max_hp * 0.49
    world_b.tick(1 / 30)
    assert world_b.boss.boss_phase == 2
    world_b.boss.take_damage(999999, attacker=hero_b)
    world_b.tick(1 / 30)
    assert world_b.boss is None
    assert 8 * 60 <= world_b.boss_respawn_timer <= 11 * 60
    assert world_b.team_buffs["A"] > 0

    # Респавн босса по таймеру.
    world_b.boss_respawn_timer = 0.01
    world_b.tick(1 / 30)
    assert world_b.boss is not None and world_b.boss.alive

    # Курьер: покупка вне базы, доставка, 3 удара, респавн.
    world_c = World(data)
    hero_c = world_c.add_player("p1", "A")
    pc = world_c.players["p1"]
    courier = next(u for u in world_c.units if u.kind == "courier")
    hero_c.pos = (32.0, 32.0)
    world_c.apply_command("p1", {"type": "buy", "item": "blade"})
    assert courier.carrying == ["blade"]
    assert "blade" not in pc.items
    courier.pos = hero_c.pos
    world_c.tick(1 / 30)
    assert "blade" in pc.items and not courier.carrying

    for _ in range(3):
        courier.take_damage(1, attacker=hero_c)
    assert not courier.alive
    courier.courier_respawn = 0.01
    world_c.tick(1 / 30)
    assert courier.alive and courier.courier_hits == 3

    print("OK: runes, boss phases/drop/respawn, courier delivery/death/respawn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
