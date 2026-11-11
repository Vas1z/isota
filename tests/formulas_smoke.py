"""Smoke-тест чистых формул: статы, урон, золото, опыт, тайминги."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.formulas import (  # noqa: E402
    ability_rank,
    armor_from_agi,
    armor_multiplier,
    assist_xp,
    attacks_per_second,
    attribute_growth,
    boss_respawn,
    damage_after_resists,
    death_gold_penalty,
    death_xp_penalty,
    evasion_chance,
    hero_damage,
    hero_kill_xp,
    neutral_stack_count,
    passive_gold_per_second,
    scaled_ability,
    spend_gold,
)


def main() -> int:
    # Броня: формула из ТЗ.
    assert abs(armor_from_agi(0.0)) < 1e-9
    assert abs(armor_from_agi(10.0) - 0.6 / 1.6) < 1e-9
    assert 0.0 < armor_multiplier(5.0) < 1.0

    # Скорость атаки: кап 2.0.
    assert abs(attacks_per_second(0.8, 0) - 0.8) < 1e-9
    assert abs(attacks_per_second(0.8, 20) - 1.0) < 1e-9
    assert attacks_per_second(1.9, 100) == 2.0

    # Атрибуты: +2 основной, +1 остальные.
    attrs = attribute_growth({"str": 10, "agi": 5, "int": 3}, "str", 4)
    assert attrs == {"str": 16.0, "agi": 8.0, "int": 6.0}

    # Урон героя.
    assert abs(hero_damage(30, 20, 0.8) - 46.0) < 1e-9

    # Типы урона.
    phys = damage_after_resists(100, "physical", armor=5)
    assert 0 < phys < 100
    mag = damage_after_resists(100, "magical", magic_resist=0.25)
    assert abs(mag - 75.0) < 1e-9
    assert damage_after_resists(100, "magical", magic_immune=True) == 0
    assert abs(damage_after_resists(100, "pure") - 100.0) < 1e-9
    assert abs(damage_after_resists(100, "pure", damage_reduction=0.5) - 50.0) < 1e-9

    # Уклонение складывается нелинейно.
    assert abs(evasion_chance([0.2, 0.2]) - 0.36) < 1e-9
    assert abs(evasion_chance([]) - 0.0) < 1e-9

    # Золото/опыт.
    assert death_gold_penalty(5) == 150
    assert abs(death_xp_penalty(200) - 20.0) < 1e-9
    assert passive_gold_per_second(599.0) == 0.0
    assert passive_gold_per_second(600.0) == 2.0
    assert hero_kill_xp(4) == 140
    assert assist_xp(140) == 70

    # Надёжное/ненадёжное золото.
    reliable, unreliable, ok = spend_gold(100.0, 30.0, 50.0)
    assert ok and abs(reliable - 80.0) < 1e-9 and unreliable == 0.0
    reliable, unreliable, ok = spend_gold(100.0, 30.0, 120.0)
    assert ok and abs(reliable - 10.0) < 1e-9 and unreliable == 0.0
    _, _, ok = spend_gold(10.0, 10.0, 50.0)
    assert not ok

    # Тайминги.
    rng = random.Random(1)
    respawn = boss_respawn(rng)
    assert 8 * 60 <= respawn <= 11 * 60
    assert neutral_stack_count(0) == 1
    assert neutral_stack_count(60) == 2
    assert neutral_stack_count(180) == 3
    assert neutral_stack_count(999) == 3

    # Ранги и Аганим.
    assert ability_rank(1) == 1
    assert ability_rank(4) == 2
    assert ability_rank(10) == 4
    base = {"damage": 100, "radius": 2.0, "mana": 50, "cooldown": 10}
    rank2 = scaled_ability(base, 2)
    assert rank2["damage"] == 130.0
    assert abs(rank2["mana"] - 55.0) < 1e-9
    assert rank2["cooldown"] == 9.0
    agha = scaled_ability(base, 4, agha=True)
    assert agha["damage"] > scaled_ability(base, 4)["damage"]
    assert agha["radius"] > scaled_ability(base, 4)["radius"]

    print("OK: formulas smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
