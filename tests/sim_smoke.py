"""Smoke-тест общей симуляции (без pygame).

Запуск из корня проекта:
    python tests/sim_smoke.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World, dist  # noqa: E402


def main() -> int:
    data = loader.load_all()
    loader.validate(data)
    spawn_a = tuple(data["map"]["spawns"]["A"])

    # 1. Инициализация и движение героя.
    world = World(data)
    hero = world.add_player("p1", "A", "Tester")
    assert sum(1 for u in world.units if u.kind == "tower") == 22
    assert sum(1 for u in world.units if u.kind == "tower" and u.team == "A") == 11
    assert sum(1 for u in world.units if u.kind == "tower" and u.team == "B") == 11
    thrones = [u for u in world.units if u.kind == "throne"]
    assert len(thrones) == 2, "expected two thrones"
    assert {u.team for u in thrones} == {"A", "B"}
    threshold = sum(int(camp.get("count", 2)) for camp in data["map"]["neutrals"])
    assert sum(
        1 for u in world.units if u.kind == "neutral" and not u.is_boss
    ) == threshold, "expected neutral camp units"
    assert sum(1 for u in world.units if u.is_boss) == 1, "expected river boss"
    mid_towers = [
        u for u in world.units
        if u.kind == "tower" and u.pos in (
            (15.9, 50.5), (21.9, 44.5), (27.9, 38.5),
            (48.1, 13.5), (42.1, 19.5), (36.1, 25.5),
        )
    ]
    assert len(mid_towers) == 6, f"expected 6 mid towers, got {len(mid_towers)}"
    world.apply_command("p1", {"type": "move", "x": 12, "y": 12})
    for _ in range(60 * 31):
        world.tick(1 / 60)
    assert world.match_time > 0.5, "game should pass the -30s countdown"
    assert hero.pos != spawn_a, "hero did not move"

    # 1b. Скорость героя по X и по Y должна быть одинаковой.
    world_axis = World(data)
    axis_hero = world_axis.add_player("p1", "A")
    world_axis.units = [axis_hero]
    axis_hero.pos = (10.0, 24.0)
    world_axis.apply_command("p1", {"type": "move", "x": 14.0, "y": 24.0})
    for _ in range(30):
        world_axis.tick(1 / 30)
    moved_x = abs(axis_hero.pos[0] - 10.0)
    axis_hero.pos = (24.0, 10.0)
    world_axis.apply_command("p1", {"type": "move", "x": 24.0, "y": 14.0})
    for _ in range(30):
        world_axis.tick(1 / 30)
    moved_y = abs(axis_hero.pos[1] - 10.0)
    assert abs(moved_x - moved_y) < 0.05, (
        f"movement is not axis-symmetric: x={moved_x:.3f}, y={moved_y:.3f}"
    )

    # 2. Добивание крипа: золото, CS и опыт рядом с героем.
    world2 = World(data)
    hero2 = world2.add_player("p1", "A")
    hero2.pos = (20.0, 20.0)
    creep = world2._make_creep("B", [(20.0 + 1, 20.0)] * 2, data["units"]["creep"])
    creep.pos = (20.0 + 1, 20.0)
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
    assert 40 <= world2.players["p1"].xp <= 48, "XP was not awarded to nearby hero"
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
    assert hero3.pos == spawn_a

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
    world4b.players["p2"].hero.pos = (spawn_a[0] + 1, spawn_a[1])
    hero4b.take_damage(99999, attacker=world4b.players["p2"].hero)
    world4b.tick(1 / 30)
    assert world4b.players["p2"].level == 2, "hero kill XP did not level up the killer"

    # 6. В каждой волне есть ranged-крипы.
    world5 = World(data)
    world5.add_player("p1", "A")
    for _ in range(int(30.5 * 60)):
        world5.tick(1 / 60)
    assert world5.match_time > 0.0
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
        if u.kind == "tower" and u.team == "A" and u.pos == (5.6, 13.3)
    )
    world6.players["p2"].hero.pos = (4.7, 10.0)  # герой ближе к вышке
    creep2 = world6._make_creep("B", [(5.2, 10.0), (5.2, 10.0)], data["units"]["creep"])
    creep2.pos = (5.2, 10.0)
    world6._add_unit(creep2)
    target = tower._find_target(world6.units)
    assert target is creep2, f"tower targeted {getattr(target, 'kind', None)} instead of creep"

    # 7b. Deny: свой крип ниже 40% HP, без золота/CS и с половиной опыта врагу.
    world8 = World(data)
    world8.add_player("p1", "A")
    world8.add_player("p2", "B")
    world8.players["p2"].hero.pos = (spawn_a[0] + 2, spawn_a[1])
    creep3 = world8._make_creep("A", [(spawn_a[0] + 1, spawn_a[1])] * 2, data["units"]["creep"])
    creep3.pos = (spawn_a[0] + 1, spawn_a[1])
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
    assert 20 <= world8.players["p2"].xp <= 24, "deny XP was not halved"
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
    enemy10.pos = (spawn_a[0] + 2, spawn_a[1])
    caster = world10.players["p1"]
    mana_before = caster.mana
    hp_before = enemy10.hp
    world10.apply_command("p1", {"type": "cast", "slot": 0, "target": enemy10.uid})
    assert caster.mana < mana_before, "ability did not spend mana"
    assert caster.cooldowns.get(0, 0) > 0, "ability cooldown was not set"
    assert enemy10.hp < hp_before, "ability did not deal damage"
    assert any(e["kind"] == "ability" for e in world10.events)

    # 7e. Ближний бой: у рыцаря удар без снаряда, у лучницы — со снарядом.
    world11 = World(data)
    melee_hero = world11.add_player("p1", "A", hero_id="knight")
    melee_hero.pos = (20.0, 20.0)
    assert melee_hero.melee, "knight should be melee"
    creep4 = world11._make_creep("B", [(21.0, 20.0)] * 2, data["units"]["creep"])
    creep4.pos = (21.0, 20.0)
    world11._add_unit(creep4)
    hp_before = creep4.hp
    world11.apply_command("p1", {"type": "attack", "target": creep4.uid})
    for _ in range(30):
        world11.tick(1 / 30)
    assert creep4.hp < hp_before, "melee hit did not deal damage"
    assert not [p for p in world11.projectiles if p.owner is melee_hero], \
        "melee attack must not create a projectile"
    assert any(e["kind"] == "melee_attack" for e in world11.events)

    world12 = World(data)
    ranged_hero = world12.add_player("p1", "A", hero_id="archer")
    ranged_hero.pos = (20.0, 20.0)
    assert not ranged_hero.melee, "archer should be ranged"
    creep5 = world12._make_creep("B", [(21.0, 20.0)] * 2, data["units"]["creep"])
    creep5.pos = (21.0, 20.0)
    world12._add_unit(creep5)
    world12.apply_command("p1", {"type": "attack", "target": creep5.uid})
    hp_before = creep5.hp
    for _ in range(15):
        world12.tick(1 / 30)
    assert [p for p in world12.projectiles if p.owner is ranged_hero], \
        "ranged hero must create a projectile"
    for _ in range(15):
        world12.tick(1 / 30)
    assert creep5.hp < hp_before
    # 7f. Крип не застревает в своей же вышке на линии.
    world13 = World(data)
    world13.add_player("p1", "A")
    tower13 = next(
        u for u in world13.units
        if u.kind == "tower" and u.team == "A" and u.pos == (5.6, 30.7)
    )
    creep6 = world13._make_creep("A", [(5.6, 13.3)], data["units"]["creep"])
    creep6.pos = tower13.pos
    creep6.waypoints = [(5.6, 13.3)]
    creep6.wp_index = 0
    world13._add_unit(creep6)
    start_pos = creep6.pos
    for _ in range(60):
        world13.tick(1 / 60)
    assert dist(creep6.pos, start_pos) > 0.5, "creep got stuck in its own tower"

    # 7g. Нейтрал умирает и респавнится на своём лагере.
    world14 = World(data)
    world14.add_player("p1", "A")
    neutral = next(u for u in world14.units if u.kind == "neutral")
    home = neutral.home_pos
    neutral.respawn_time = 0.5
    neutral.take_damage(99999)
    world14.tick(1 / 30)
    assert not neutral.alive
    for _ in range(30):
        world14.tick(1 / 30)
    revived = [
        u for u in world14.units
        if u.kind == "neutral" and u.home_pos == home
        and u.neutral_type == neutral.neutral_type
    ]
    assert revived, "neutral did not respawn at its camp"

    # 7h. Герой S: три мгновенных разреза по направлению взгляда,
    # пассивка на души и ультимейт с задержкой.
    world_s = World(data)
    s_hero = world_s.add_player("p1", "A", hero_id="s")
    s_player = world_s.players["p1"]
    target_s = world_s.add_player("p2", "B", hero_id="knight")
    assert not s_hero.melee, "S should be a ranged demon"
    assert s_hero.atk_range > 2.0, "S attack range is too short"

    s_hero.facing = (1.0, 0.0)

    # Q — ближний разрез ровно впереди, клик по точке игнорируется.
    target_s.pos = (s_hero.pos[0] + 1.0, s_hero.pos[1])
    target_s.hp = target_s.max_hp
    hp_before = target_s.hp
    mana_before = s_player.mana
    world_s.apply_command(
        "p1", {"type": "cast", "slot": 0, "x": s_hero.pos[0] - 5.0, "y": s_hero.pos[1]},
    )
    assert target_s.hp < hp_before, "S Q did not hit at its fixed distance"
    assert s_player.mana < mana_before and s_player.cooldowns.get(0, 0) > 0

    # W — средний разрез на фиксированной дистанции.
    s_player.mana = s_player.max_mana
    s_player.cooldowns.clear()
    target_s.hp = target_s.max_hp
    target_s.pos = (s_hero.pos[0] + 2.25, s_hero.pos[1])
    hp_before = target_s.hp
    world_s.apply_command("p1", {"type": "cast", "slot": 1})
    assert target_s.hp < hp_before, "S W did not hit at its fixed distance"

    # E — дальний разрез со снижением брони.
    s_player.mana = s_player.max_mana
    s_player.cooldowns.clear()
    target_s.hp = target_s.max_hp
    target_s.armor_debuff = 0.0
    target_s.armor_debuff_timer = 0.0
    target_s.pos = (s_hero.pos[0] + 3.5, s_hero.pos[1])
    hp_before = target_s.hp
    world_s.apply_command("p1", {"type": "cast", "slot": 2})
    assert target_s.hp < hp_before, "S E did not hit at its fixed distance"
    assert target_s.armor_debuff > 0, "S E did not reduce armor"

    # Направление разреза меняется вместе с движением героя.
    s_player.cooldowns.clear()
    s_player.mana = s_player.max_mana
    target_s.hp = target_s.max_hp
    target_s.pos = (s_hero.pos[0], s_hero.pos[1] + 1.0)
    world_s.apply_command("p1", {"type": "move", "x": s_hero.pos[0], "y": s_hero.pos[1] + 3.0})
    for _ in range(6):
        world_s.tick(1 / 30)
    world_s.apply_command("p1", {"type": "stop"})
    world_s.apply_command("p1", {"type": "cast", "slot": 0})
    assert target_s.hp < hp_before, "S raze did not follow hero facing"

    # Пассивка: +1 душа и +2 урона за убийство, но не больше 20.
    dmg_before = s_hero.atk_dmg
    creep_s = world_s._make_creep("B", [(s_hero.pos[0] + 1, s_hero.pos[1])] * 2,
                                  data["units"]["creep"])
    creep_s.pos = (s_hero.pos[0] + 1, s_hero.pos[1])
    world_s._add_unit(creep_s)
    creep_s.take_damage(99999, attacker=s_hero)
    world_s.tick(1 / 30)
    assert s_player.soul_stacks == 1, "S passive did not gain a soul"
    assert s_hero.atk_dmg > dmg_before, "S passive did not add damage"

    s_player.soul_stacks = 20
    world_s._add_soul_stack(s_player)
    assert s_player.soul_stacks == 20, "S passive exceeded 20 souls"

    # Ультимейт: герой стоит во время подготовки, затем 18 душ во все стороны.
    world_su = World(data)
    s_hero_u = world_su.add_player("p1", "A", hero_id="s")
    s_player_u = world_su.players["p1"]
    target_u = world_su.add_player("p2", "B", hero_id="knight")
    target_u.pos = (s_hero_u.pos[0] + 2.0, s_hero_u.pos[1])
    target_u.max_hp = 5000.0
    target_u.hp = 5000.0
    s_player_u.soul_stacks = 10
    s_player_u.cooldowns.clear()
    hp_before = target_u.hp
    cast_pos = s_hero_u.pos
    world_su.apply_command("p1", {"type": "cast", "slot": 3})
    assert world_su.pending_bursts, "S ultimate was not delayed"
    assert s_hero_u.cast_lock_timer > 0, "S ultimate did not lock the caster"
    world_su.apply_command("p1", {"type": "move", "x": s_hero_u.pos[0] + 5.0,
                                  "y": s_hero_u.pos[1] + 5.0})
    for _ in range(10):
        world_su.tick(1 / 30)
    assert dist(s_hero_u.pos, cast_pos) < 0.01, "S moved during ultimate windup"

    for _ in range(25):
        world_su.tick(1 / 30)
    assert len(world_su.souls) == 18, "S ultimate should release 18 soul lines"
    for _ in range(30):
        world_su.tick(1 / 30)
    assert target_u.hp < hp_before, "S ultimate souls did not damage on contact"
    assert target_u.slow_timer > 0, "S ultimate souls did not slow on contact"
    snap_s = world_su.snapshot()
    assert snap_s["players"]["p1"]["souls"] == 10, "snapshot misses S soul stacks"
    hero_snap = next(u for u in snap_s["units"] if u["id"] == s_hero_u.uid)
    assert "facing" in hero_snap, "snapshot misses hero facing"

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
