"""Smoke-тест экономики: золото, опыт, штрафы, стаки."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()

    # Крип: золото 38-42 и опыт 40-48.
    world = World(data)
    hero = world.add_player("p1", "A", hero_id="knight")
    player = world.players["p1"]
    creep = world._make_creep("B", [(hero.pos[0] + 1, hero.pos[1])] * 2,
                              data["units"]["creep"])
    creep.pos = (hero.pos[0] + 1, hero.pos[1])
    creep.hp = 1
    world._add_unit(creep)
    gold_before = player.unreliable_gold
    creep.take_damage(99999, attacker=hero)
    world.tick(1 / 30)
    assert 38 <= player.unreliable_gold - gold_before <= 42
    assert 40 <= player.xp <= 48
    assert player.cs == 1

    # Рэнжед-крип: 43-48.
    world_r = World(data)
    hero_r = world_r.add_player("p1", "A")
    player_r = world_r.players["p1"]
    ranged = world_r._make_creep("B", [(hero_r.pos[0] + 1, hero_r.pos[1])] * 2,
                                 data["units"]["creep_ranged"], kind="creep_ranged")
    ranged.pos = (hero_r.pos[0] + 1, hero_r.pos[1])
    ranged.hp = 1
    world_r._add_unit(ranged)
    before = player_r.unreliable_gold
    ranged.take_damage(99999, attacker=hero_r)
    world_r.tick(1 / 30)
    assert 43 <= player_r.unreliable_gold - before <= 48

    # Нейтрал: 50-70.
    world_n = World(data)
    hero_n = world_n.add_player("p1", "A")
    player_n = world_n.players["p1"]
    neutral = next(u for u in world_n.units if u.kind == "neutral" and not u.is_boss)
    neutral.hp = 1
    before = player_n.unreliable_gold
    neutral.take_damage(99999, attacker=hero_n)
    world_n.tick(1 / 30)
    assert 50 <= player_n.unreliable_gold - before <= 70

    # Башня: 250 команде, надёжное золото.
    world_t = World(data)
    hero_t = world_t.add_player("p1", "A")
    player_t = world_t.players["p1"]
    tower = next(u for u in world_t.units
                 if u.kind == "tower" and u.team == "B")
    reliable_before = player_t.reliable_gold
    tower.take_damage(99999, attacker=hero_t)
    world_t.tick(1 / 30)
    assert player_t.reliable_gold - reliable_before == 250

    # Убийство героя: +175 надёжного золота, −30 золота и −10% опыта у жертвы.
    world_h = World(data)
    hero_a = world_h.add_player("p1", "A")
    hero_b = world_h.add_player("p2", "B")
    pa = world_h.players["p1"]
    pb = world_h.players["p2"]
    pb.xp = 100.0
    reliable_before = pa.reliable_gold
    unreliable_before = pb.unreliable_gold
    hero_b.take_damage(99999, attacker=hero_a)
    world_h.tick(1 / 30)
    assert pa.reliable_gold - reliable_before >= 175
    assert pb.unreliable_gold == unreliable_before - 30
    assert pb.xp <= 90.0

    # Надёжное золото тратится после ненадёжного.
    world_s = World(data)
    world_s.add_player("p1", "A")
    ps = world_s.players["p1"]
    ps.reliable_gold = 100.0
    ps.unreliable_gold = 100.0
    ps.gold = 200.0
    world_s.apply_command("p1", {"type": "buy", "item": "scroll"})
    assert ps.reliable_gold == 50.0 and ps.unreliable_gold == 0.0
    assert ps.gold == 50.0

    # Пассивный доход +2/сек после 10-й минуты.
    world_p = World(data)
    world_p.add_player("p1", "A")
    pp = world_p.players["p1"]
    world_p.match_time = 600.0
    before = pp.unreliable_gold
    for _ in range(10):
        world_p.tick(0.1)
    assert abs((pp.unreliable_gold - before) - 2.0) < 0.05

    # Стаки нейтралов: +1 набор после 60 секунд без урона.
    world_c = World(data)
    world_c.add_player("p1", "A")
    camp_id = next(iter(world_c.camps))
    camp = world_c.camps[camp_id]
    count_before = sum(
        1 for u in world_c.units if u.alive and u.camp_id == camp_id
    )
    world_c.match_time = 61.0
    world_c.camp_touched_at[camp_id] = 0.0
    world_c._update_camp_stacks()
    count_after = sum(
        1 for u in world_c.units if u.alive and u.camp_id == camp_id
    )
    assert count_after == count_before + int(camp.get("count", 2))
    assert world_c.camp_stacks[camp_id] == 2

    print("OK: economy, reliable gold, death penalty, passive income, stacks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
