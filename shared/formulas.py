"""Чистые формулы MOBA: статы, урон, золото, опыт и тайминги.

Модуль не зависит от pygame и World, поэтому его удобно тестировать отдельно.
"""

from __future__ import annotations

import math
import random
from typing import Iterable, Tuple

# ---------- Статы ----------

def armor_from_agi(agi: float) -> float:
    """Броня по ТЗ: (0.06 * agi) / (1 + 0.06 * |agi|)."""
    return (0.06 * agi) / (1.0 + 0.06 * abs(agi))


def armor_multiplier(armor: float) -> float:
    """Множитель физического урона. 6 брони ≈ 26% снижения."""
    return 100.0 / (100.0 + armor * 6.0)


def attacks_per_second(base_as: float, agi: float) -> float:
    """Скорость атаки: базовая + ловкость/100, кап 2.0."""
    return max(0.1, min(2.0, base_as + agi / 100.0))


def attribute_growth(base: dict, primary: str, level: int) -> dict:
    """+2 к основному атрибуту и +1 к остальным за уровень."""
    level = max(1, int(level))
    out = {}
    for key in ("str", "agi", "int"):
        step = 2.0 if key == primary else 1.0
        out[key] = float(base.get(key, 0)) + step * (level - 1)
    return out


def hero_damage(base_damage: float, primary_value: float, coefficient: float) -> float:
    return float(base_damage) + float(primary_value) * float(coefficient)


# ---------- Урон ----------

DAMAGE_TYPES = ("physical", "magical", "pure")


def damage_after_resists(
    damage: float,
    damage_type: str = "physical",
    armor: float = 0.0,
    magic_resist: float = 0.25,
    magic_immune: bool = False,
    damage_reduction: float = 0.0,
) -> float:
    """Итоговый урон после брони/магреза/иммунитета/дисперсии."""
    damage = max(0.0, float(damage))
    if damage_type == "physical":
        damage *= armor_multiplier(float(armor))
    elif damage_type == "magical":
        if magic_immune:
            return 0.0
        damage *= max(0.0, 1.0 - float(magic_resist))
    elif damage_type == "pure":
        pass
    else:
        raise ValueError(f"unknown damage type: {damage_type}")
    damage *= max(0.0, 1.0 - min(0.95, float(damage_reduction)))
    return max(0.0, damage)


def evasion_chance(chances: Iterable[float]) -> float:
    """Сложение уклонений: 1 - Π(1 - p)."""
    miss = 1.0
    for chance in chances:
        miss *= 1.0 - max(0.0, min(0.95, float(chance)))
    return 1.0 - miss


def roll_evasion(chance: float, rng: random.Random | None = None) -> bool:
    rng = rng or random
    return rng.random() < max(0.0, min(0.95, float(chance)))


def roll_crit(chance: float, rng: random.Random | None = None) -> bool:
    rng = rng or random
    return rng.random() < max(0.0, min(1.0, float(chance)))


def crit_damage(damage: float, multiplier: float = 1.75) -> float:
    return float(damage) * max(1.0, float(multiplier))


# ---------- Золото и опыт ----------

CREEP_GOLD = {
    "creep": (38, 42),
    "creep_ranged": (43, 48),
    "neutral": (50, 70),
    "tower": (250, 250),
}

CREEP_XP = {
    "creep": (40, 48),
    "creep_ranged": (52, 60),
    "neutral": (50, 70),
}


def roll_gold(kind: str, rng: random.Random | None = None) -> int:
    rng = rng or random
    low, high = CREEP_GOLD.get(kind, (0, 0))
    return int(rng.randint(low, high))


def roll_xp(kind: str, rng: random.Random | None = None) -> int:
    rng = rng or random
    low, high = CREEP_XP.get(kind, (0, 0))
    return int(rng.randint(low, high))


def hero_kill_xp(victim_level: int) -> int:
    return 100 + 10 * max(1, int(victim_level))


def assist_xp(kill_xp: float) -> int:
    return int(kill_xp * 0.5)


def death_gold_penalty(level: int) -> int:
    return 30 * max(1, int(level))


def death_xp_penalty(xp: float) -> float:
    return max(0.0, float(xp)) * 0.10


def passive_gold_per_second(match_time: float) -> float:
    """+2 золота/сек после 10-й минуты."""
    return 2.0 if match_time >= 600.0 else 0.0


def spend_gold(reliable: float, unreliable: float, cost: float) -> Tuple[float, float, bool]:
    """Сначала тратится ненадёжное золото, затем надёжное."""
    cost = max(0.0, float(cost))
    if reliable + unreliable + 1e-9 < cost:
        return reliable, unreliable, False
    spend_unreliable = min(unreliable, cost)
    unreliable -= spend_unreliable
    cost -= spend_unreliable
    reliable -= cost
    return max(0.0, reliable), max(0.0, unreliable), True


# ---------- Тайминги ----------

RUNE_RESPAWN = 120.0
BOSS_RESPAWN_MIN = 8 * 60.0
BOSS_RESPAWN_MAX = 11 * 60.0
COURIER_RESPAWN = 60.0
NEUTRAL_STACK_INTERVAL = 60.0
NEUTRAL_STACK_MAX = 3


def boss_respawn(rng: random.Random | None = None) -> float:
    rng = rng or random
    return rng.uniform(BOSS_RESPAWN_MIN, BOSS_RESPAWN_MAX)


def neutral_stack_count(untouched_for: float) -> int:
    return min(NEUTRAL_STACK_MAX, 1 + int(max(0.0, untouched_for) // NEUTRAL_STACK_INTERVAL))


# ---------- Способности ----------

def ability_rank(level: int) -> int:
    """4 ранга способности: 1/4/7/10 уровень героя."""
    return max(1, min(4, 1 + (max(1, int(level)) - 1) // 3))


def scaled_ability(ability: dict, rank: int, agha: bool = False) -> dict:
    """Возвращает копию способности с множителями ранга и Аганима."""
    rank = max(1, min(4, int(rank)))
    out = dict(ability)
    damage_mult = 1.0 + 0.30 * (rank - 1)
    cooldown_mult = 1.0 - 0.10 * (rank - 1)
    mana_mult = 1.0 + 0.10 * (rank - 1)
    if agha:
        damage_mult *= 1.50
    for key in ("damage", "amount", "heal"):
        if key in out:
            out[key] = float(out[key]) * damage_mult
    if "radius" in out:
        out["radius"] = float(out["radius"]) * (1.20 if agha else 1.0)
    out["mana"] = float(out.get("mana", 0)) * mana_mult
    out["cooldown"] = float(out.get("cooldown", 5.0)) * cooldown_mult
    out["rank"] = rank
    out["agha"] = bool(agha)
    return out


def talent_effect_value(effect: dict) -> float:
    return float(effect.get("value", 0.0))
