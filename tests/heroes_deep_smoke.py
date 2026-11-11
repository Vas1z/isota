"""Smoke-тест глубины героев: статы, таланты, Аганим/Осколок, ранги способностей."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared import formulas  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()

    # Атрибуты: +2 основной, +1 остальные.
    world = World(data)
    hero = world.add_player("p1", "A", hero_id="knight")
    player = world.players["p1"]
    player.level = 4
    world._recompute_hero(player)
    assert player.str == 30.0, player.str
    assert player.agi == 17.0, player.agi
    assert player.int == 17.0, player.int

    # Урон = база + основной атрибут × коэффициент героя.
    meta = data["heroes_meta"]["knight"]
    expected_damage = 30 + player.str * meta["coefficient"]
    assert abs(hero.atk_dmg - expected_damage) < 0.01

    # Броня по формуле.
    assert abs(hero.armor - (3.0 + formulas.armor_from_agi(player.agi))) < 0.01

    # Талант 10 уровня.
    player.level = 9
    player.xp = 0.0
    player.xp_next = 10.0
    world._add_xp(player, 10.0)
    assert player.level == 10
    assert 10 in player.pending_talents
    str_before = player.str
    world.apply_command("p1", {"type": "talent", "level": 10, "choice": 0})
    assert 10 not in player.pending_talents
    assert player.str == str_before + 8.0

    # Аганим и Осколок: лимит 2 на команду.
    world_a = World(data)
    for pid, name in (("p1", "A1"), ("p2", "A2"), ("p3", "A3")):
        world_a.add_player(pid, "A", name)
        world_a.players[pid].unreliable_gold = 5000.0
        world_a.players[pid].gold = 5000.0
    for pid in ("p1", "p2", "p3"):
        world_a.apply_command(pid, {"type": "buy", "item": "agha_core"})
    assert world_a.players["p1"].has_agha
    assert world_a.players["p2"].has_agha
    assert not world_a.players["p3"].has_agha
    assert world_a.team_agha["A"] == 2

    # Ранг способности растёт с уровнем героя.
    world_low = World(data)
    caster_low = world_low.add_player("p1", "A", hero_id="knight")
    target_low = world_low.add_player("p2", "B", hero_id="knight")
    target_low.pos = (caster_low.pos[0] + 2.0, caster_low.pos[1])
    hp_before = target_low.hp
    world_low.apply_command("p1", {"type": "cast", "slot": 0,
                                   "target": target_low.uid})
    low_damage = hp_before - target_low.hp

    world_high = World(data)
    caster_high = world_high.add_player("p1", "A", hero_id="knight")
    target_high = world_high.add_player("p2", "B", hero_id="knight")
    target_high.pos = (caster_high.pos[0] + 2.0, caster_high.pos[1])
    world_high.players["p1"].level = 10
    world_high._recompute_hero(world_high.players["p1"])
    hp_before = target_high.hp
    world_high.apply_command("p1", {"type": "cast", "slot": 0,
                                    "target": target_high.uid})
    high_damage = hp_before - target_high.hp

    assert high_damage > low_damage * 1.5, (low_damage, high_damage)
    print("OK: hero stats, talents, agha limit, ability ranks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
