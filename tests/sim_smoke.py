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
    assert sum(1 for u in world.units if u.kind == "tower") == 14
    thrones = [u for u in world.units if u.kind == "throne"]
    assert len(thrones) == 2, "expected two thrones"
    assert {u.team for u in thrones} == {"A", "B"}
    mid_towers = [
        u for u in world.units
        if u.kind == "tower" and u.pos in (
            (6.5, 17.5), (9.0, 15.0), (17.5, 6.5), (15.0, 9.0),
        )
    ]
    assert len(mid_towers) == 4, f"expected 4 mid towers, got {len(mid_towers)}"
    world.apply_command("p1", {"type": "move", "x": 12, "y": 12})
    for _ in range(60 * 12):
        world.tick(1 / 60)
    assert world.match_time >= 11.9
    assert hero.pos != (4.0, 20.0), "hero did not move"
    assert world.players["p1"].gold >= 11, "passive gold is broken"

    # 2. Добивание крипа: золото, CS и опыт рядом с героем.
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
    assert int(world2.players["p1"].gold) >= 5, "bounty was not awarded"
    assert world2.players["p1"].xp == 20, "XP was not awarded to nearby hero"
    assert any(e["kind"] == "bounty" for e in world2.events)

    # 3. Уровень: растут атрибуты и производные статы.
    player = world2.players["p1"]
    hp_before = hero2.max_hp
    dmg_before = hero2.atk_dmg
    armor_before = hero2.armor
    str_before = player.str
    world2._add_xp(player, 100)  # 20 уже есть, нужно 100 до 2 уровня
    assert player.level == 2, "hero did not level up"
    assert player.str > str_before, "strength did not grow"
    assert hero2.max_hp > hp_before, "HP growth is broken"
    assert hero2.atk_dmg > dmg_before, "damage growth is broken"
    assert hero2.armor > armor_before, "armor growth is broken"
    assert any(e["kind"] == "level_up" for e in world2.events)

    # 4. Смерть героя и респавн.
    world3 = World(data)
    hero3 = world3.add_player("p1", "A")
    enemy = world3.add_player("p2", "B")
    gold_before = world3.players["p2"].gold
    hero3.take_damage(99999, attacker=enemy)
    world3.tick(1 / 30)
    assert not hero3.alive
    assert world3.players["p1"].deaths == 1
    assert world3.players["p2"].kills == 1
    assert world3.players["p2"].gold >= gold_before + 175, "hero kill gold was not awarded"
    assert world3.players["p1"].respawn_timer > 0

    for _ in range(30 * 6):
        world3.tick(1 / 30)
    assert hero3.alive, "hero did not respawn"
    assert hero3.hp == hero3.max_hp
    assert hero3.pos == (4.0, 20.0)

    # 5. Время респавна растёт с уровнем.
    world4 = World(data)
    hero4 = world4.add_player("p1", "A")
    world4.add_player("p2", "B")
    world4.players["p1"].level = 3
    hero4.take_damage(99999, attacker=world4.players["p2"].hero)
    world4.tick(1 / 30)
    assert world4.players["p1"].respawn_timer > 6.5, "respawn did not scale with level"

    # 5b. Опыт за убийство героя получает вражеский герой рядом.
    world4b = World(data)
    hero4b = world4b.add_player("p1", "A")
    world4b.add_player("p2", "B")
    world4b.players["p2"].hero.pos = (5.0, 20.0)
    hero4b.take_damage(99999, attacker=world4b.players["p2"].hero)
    world4b.tick(1 / 30)
    assert world4b.players["p2"].level == 2, "hero kill XP did not level up the killer"

    # 6. В каждой волне есть ranged-крипы.
    world5 = World(data)
    world5.add_player("p1", "A")
    for _ in range(610):
        world5.tick(1 / 60)
    ranged = [u for u in world5.units if u.kind == "creep_ranged"]
    melee = [u for u in world5.units if u.kind == "creep"]
    assert len(ranged) == 6, f"expected 6 ranged creeps, got {len(ranged)}"
    assert len(melee) == 24, f"expected 24 melee creeps, got {len(melee)}"

    # 7. Вышка сначала стреляет по крипам, а не по герою.
    world6 = World(data)
    world6.add_player("p1", "A")
    world6.add_player("p2", "B")
    tower = next(
        u for u in world6.units
        if u.kind == "tower" and u.team == "A" and u.pos == (1.5, 8.5)
    )
    world6.players["p2"].hero.pos = (2.0, 8.5)  # герой ближе к вышке
    creep2 = world6._make_creep("B", [(2.5, 8.5), (2.5, 8.5)], data["units"]["creep"])
    creep2.pos = (2.5, 8.5)
    world6._add_unit(creep2)
    target = tower._find_target(world6.units)
    assert target is creep2, f"tower targeted {getattr(target, 'kind', None)} instead of creep"

    # 7b. Deny: свой крип ниже 40% HP, без золота/CS и с половиной опыта врагу.
    world8 = World(data)
    world8.add_player("p1", "A")
    world8.add_player("p2", "B")
    world8.players["p2"].hero.pos = (6.0, 20.0)
    creep3 = world8._make_creep("A", [(5, 20), (5, 20)], data["units"]["creep"])
    creep3.pos = (5.0, 20.0)
    creep3.hp = 10.0
    world8._add_unit(creep3)
    world8.apply_command("p1", {"type": "deny", "target": creep3.uid})
    for _ in range(120):
        world8.tick(1 / 60)
        if not creep3.alive:
            break
    assert not creep3.alive, "deny did not kill the creep"
    assert world8.players["p1"].denies == 1, "deny was not counted"
    assert world8.players["p1"].cs == 0, "deny gave CS"
    assert world8.players["p2"].xp == 10, "deny XP was not halved"
    assert any(e["kind"] == "deny" for e in world8.events)

    # 7c. Магазин: ботинки дают скорость, повторная покупка unique отклоняется.
    world9 = World(data)
    hero9 = world9.add_player("p1", "A")
    player9 = world9.players["p1"]
    speed_before = hero9.speed
    world9.apply_command("p1", {"type": "buy", "item": "boots"})
    assert "boots" in player9.items
    assert hero9.speed > speed_before, "boots did not increase speed"
    world9.apply_command("p1", {"type": "buy", "item": "boots"})
    assert player9.items.count("boots") == 1
    assert any(e["kind"] == "shop_error" for e in world9.events)

    # 7d. Способность: урон, мана и кулдаун.
    world10 = World(data)
    world10.add_player("p1", "A")
    world10.add_player("p2", "B")
    enemy10 = world10.players["p2"].hero
    enemy10.pos = (6.0, 20.0)
    caster = world10.players["p1"]
    mana_before = caster.mana
    hp_before = enemy10.hp
    world10.apply_command("p1", {"type": "cast", "slot": 0, "target": enemy10.uid})
    assert caster.mana < mana_before, "ability did not spend mana"
    assert caster.cooldowns.get(0, 0) > 0, "ability cooldown was not set"
    assert enemy10.hp < hp_before, "ability did not deal damage"
    assert any(e["kind"] == "ability" for e in world10.events)

    # 8. Уничтожение трона завершает матч и замораживает симуляцию.
    world7 = World(data)
    world7.add_player("p1", "A")
    world7.add_player("p2", "B")
    throne_b = next(u for u in world7.units if u.kind == "throne" and u.team == "B")
    throne_b.take_damage(99999)
    world7.tick(1 / 30)
    assert world7.match_over, "match did not end after throne destruction"
    assert world7.winner == "A", "wrong winner"
    assert any(e["kind"] == "match_end" for e in world7.events)

    frozen_time = world7.match_time
    world7.tick(1 / 30)
    assert world7.match_time == frozen_time, "simulation continued after match end"

    snap7 = world7.snapshot()
    assert snap7["over"] is True and snap7["winner"] == "A"
    assert any(u["id"] == throne_b.uid and not u["alive"] for u in snap7["units"])

    # 9. Снапшот содержит нужные поля.
    snap = world3.snapshot()
    assert {"tick", "time", "over", "winner", "units", "projectiles", "players"} <= set(snap)
    me = snap["players"]["p1"]
    assert me["hero"] == hero3.uid
    assert {"level", "xp", "xp_next"} <= set(me)
    assert any(u["id"] == hero3.uid for u in snap["units"])

    print("OK: simulation smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
