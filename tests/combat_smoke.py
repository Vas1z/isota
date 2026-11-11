"""Smoke-тест боя: типы урона, статусы, уклонение, отражение, орбы."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World, apply_orb_effect  # noqa: E402


def main() -> int:
    data = loader.load_all()

    world = World(data)
    hero_a = world.add_player("p1", "A", hero_id="knight")
    hero_b = world.add_player("p2", "B", hero_id="knight")

    # Физический урон режется бронёй, магический — магрезом, чистый — нет.
    hp = hero_b.hp
    hero_b.armor = 5.0
    hero_b.magic_resist = 0.25
    hero_b.damage_reduction = 0.0
    hero_b.take_damage(100.0, damage_type="physical")
    phys_loss = hp - hero_b.hp
    hero_b.hp = hp
    hero_b.take_damage(100.0, damage_type="magical")
    mag_loss = hp - hero_b.hp
    hero_b.hp = hp
    hero_b.take_damage(100.0, damage_type="pure")
    pure_loss = hp - hero_b.hp
    assert mag_loss == 75.0
    assert pure_loss == 100.0
    assert 0 < phys_loss < pure_loss

    # Иммунитет к магии.
    hero_b.hp = hp
    hero_b.magic_immune_timer = 5.0
    hero_b.take_damage(100.0, damage_type="magical")
    assert hero_b.hp == hp
    hero_b.magic_immune_timer = 0.0

    # Уклонение.
    import shared.formulas as formulas
    old_evasion = formulas.roll_evasion
    formulas.roll_evasion = lambda chance: True
    hero_b.evasion = 1.0
    hp = hero_b.hp
    hero_b.take_damage(100.0, attacker=hero_a, damage_type="physical")
    assert hero_b.hp == hp
    hero_b.evasion = 0.0
    formulas.roll_evasion = old_evasion

    # Отражение.
    hero_b.reflect = 0.5
    hero_a.innate_type = ""
    hero_b.innate_type = ""
    hp_attacker = hero_a.hp
    hero_b.take_damage(100.0, attacker=hero_a, damage_type="pure")
    assert abs((hp_attacker - hero_a.hp) - 50.0) < 0.01
    hero_b.reflect = 0.0

    # Врождённая защита от первого удара.
    hero_b.hp = hp
    hero_b.innate_type = "first_hit_block"
    hero_b.innate_value = 0.5
    hero_b.first_hit_block_timer = 0.0
    hero_b.take_damage(100.0, attacker=hero_a, damage_type="pure")
    first_loss = hp - hero_b.hp
    hero_b.take_damage(100.0, attacker=hero_a, damage_type="pure")
    second_loss = hero_b.hp  # placeholder
    assert first_loss == 50.0

    # Статусы блокируют каст и движение.
    mana_before = world.players["p2"].mana
    hero_b.apply_silence(2.0)
    world.apply_command("p2", {"type": "cast", "slot": 0, "target": hero_a.uid})
    assert world.players["p2"].mana == mana_before
    hero_b.apply_root(2.0)
    start = hero_b.pos
    world.apply_command("p2", {"type": "move", "x": hero_b.pos[0] + 4, "y": hero_b.pos[1]})
    world.tick(1 / 30)
    assert hero_b.pos == start
    hero_b.silence_timer = 0.0
    hero_b.root_timer = 0.0

    # Орб-эффекты.
    target = world.add_player("p3", "B", hero_id="archer")
    target.apply_slow(1.0, 0.0)
    apply_orb_effect(hero_a, target, {"type": "slow", "value": 0.4, "duration": 2.0})
    assert target.slow_mult <= 0.4 and target.slow_timer > 0
    apply_orb_effect(hero_a, target, {"type": "armor_break", "value": 5, "duration": 4.0})
    assert target.armor_debuff == 5.0

    world_chain = World(data)
    owner = world_chain.add_player("p1", "A", hero_id="knight")
    first = world_chain.add_player("p2", "B", hero_id="archer")
    second = world_chain.add_player("p3", "B", hero_id="archer")
    owner.pos = (20.0, 20.0)
    first.pos = (20.5, 20.0)
    second.pos = (21.0, 20.0)
    world_chain.units = [owner, first, second]
    apply_orb_effect(owner, first, {"type": "chain", "chance": 1.0,
                                    "damage": 30, "jumps": 2}, world_chain.units)
    assert second.hp < second.max_hp

    print("OK: damage types, immunity, evasion, reflect, statuses, orbs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
