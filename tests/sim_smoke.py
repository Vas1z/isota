"""Smoke-тест общей симуляции (без pygame).

Запуск из корня проекта:
    python tests/sim_smoke.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()
    loader.validate(data)

    # 1. Инициализация и движение героя.
    world = World(data)
    hero = world.add_player("p1", "A", "Tester")
    assert sum(1 for u in world.units if u.kind == "tower") == 10
    world.apply_command("p1", {"type": "move", "x": 12, "y": 12})
    for _ in range(60 * 20):
        world.tick(1 / 60)
    assert world.match_time >= 19.9
    assert hero.pos != (4.0, 20.0), "hero did not move"
    assert world.players["p1"].gold >= 19, "passive gold is broken"

    # 2. Добивание крипа даёт золото и CS.
    world2 = World(data)
    hero2 = world2.add_player("p1", "A")
    creep = world2._make_creep("B", [(5, 20), (5, 20)], data["units"]["creep"])
    creep.pos = (6, 20)
    creep.hp = 1
    world2._add_unit(creep)
    world2.apply_command("p1", {"type": "attack", "target": creep.uid})
    for _ in range(120):
        world2.tick(1 / 60)
        if not creep.alive:
            break
    assert not creep.alive, "hero did not kill the creep"
    assert world2.players["p1"].cs == 1, "CS was not awarded"
    assert int(world2.players["p1"].gold) == 5, "bounty was not awarded"
    assert any(e["kind"] == "bounty" for e in world2.events)

    # 3. Смерть героя и респавн.
    world3 = World(data)
    hero3 = world3.add_player("p1", "A")
    enemy = world3.add_player("p2", "B")
    hero3.take_damage(99999, attacker=enemy)
    world3.tick(1 / 30)
    assert not hero3.alive
    assert world3.players["p1"].deaths == 1
    assert world3.players["p2"].kills == 1
    assert world3.players["p1"].respawn_timer > 0

    for _ in range(30 * 6):
        world3.tick(1 / 30)
    assert hero3.alive, "hero did not respawn"
    assert hero3.hp == hero3.max_hp
    assert hero3.pos == (4.0, 20.0)

    # 4. Снапшот содержит нужные поля.
    snap = world3.snapshot()
    assert {"tick", "time", "units", "projectiles", "players"} <= set(snap)
    me = snap["players"]["p1"]
    assert me["hero"] == hero3.uid
    assert any(u["id"] == hero3.uid for u in snap["units"])

    print("OK: simulation smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
