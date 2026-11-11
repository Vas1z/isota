"""Генерирует data/heroes_meta.json: innate, таланты, тайминги атаки."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEROES = ROOT / "data" / "heroes.json"
OUT = ROOT / "data" / "heroes_meta.json"

INNATES = {
    "knight": ("Клятва щита", "Каждый 8-й полученный удар режется на 50%.", "first_hit_block", 0.5),
    "archer": ("Тень листвы", "+10% уклонения.", "evasion", 0.10),
    "pyromancer": ("Тлеющий след", "Способности поджигают цель на 10 урона за 3 секунды.", "spell_burn", 10),
    "frost_mage": ("Вечная мерзлота", "Замедления длятся на 1 секунду дольше.", "slow_duration", 1.0),
    "berserker": ("Кровавый азарт", "Ниже 35% HP скорость атаки растёт на 50%.", "low_hp_as", 0.5),
    "guardian": ("Каменная аура", "Соратники рядом получают +2 брони.", "aura_armor", 2),
    "assassin": ("Удар в спину", "+15% урона по цели, если удар нанесён сзади.", "backstab", 0.15),
    "warlock": ("Печать крови", "15% урона способностей возвращается здоровьем.", "spell_lifesteal", 0.15),
    "monk": ("Внутренний покой", "+10% сопротивления магии.", "magic_resist", 0.10),
    "sniper": ("Дальний глаз", "+0.5 к дальности атаки.", "attack_range", 0.5),
    "s": ("Пожирание душ", "Души за убийства дают дополнительный урон.", "soul_harvest", 2.0),
}

COEFF = {
    "knight": 0.90, "archer": 1.00, "pyromancer": 0.85, "frost_mage": 0.85,
    "berserker": 0.95, "guardian": 0.85, "assassin": 1.05, "warlock": 0.85,
    "monk": 0.90, "sniper": 1.00, "s": 0.90,
}


def make_talents(hero_id: str, name: str, primary: str, level: int):
    if level == 10:
        return [
            {"name": f"{name}: прилив {primary}", "desc": f"+8 к основному атрибуту ({primary}).",
             "effect": {"type": "stat", "stat": primary, "value": 8}},
            {"name": f"{name}: запас сил", "desc": "+150 к максимальному HP.",
             "effect": {"type": "hp", "value": 150}},
        ]
    if level == 15:
        return [
            {"name": f"{name}: оберег", "desc": "+10% сопротивления магии.",
             "effect": {"type": "magic_resist", "value": 0.10}},
            {"name": f"{name}: ярость", "desc": "+15% скорости атаки.",
             "effect": {"type": "attack_speed", "value": 0.15}},
        ]
    return [
        {"name": f"{name}: усиление чар", "desc": "+20% урона способностей.",
         "effect": {"type": "spell_amp", "value": 0.20}},
        {"name": f"{name}: точный удар", "desc": "+25% шанса критического удара.",
         "effect": {"type": "crit", "value": 0.25}},
    ]


def main() -> None:
    data = json.loads(HEROES.read_text(encoding="utf-8"))
    out = {}
    for hero_id, hero in data["heroes"].items():
        primary = hero.get("primary", "str")
        name = hero.get("name", hero_id)
        innate_name, innate_desc, innate_type, innate_value = INNATES.get(
            hero_id, ("Дар", "Небольшой пассивный бонус.", "stat", 0)
        )
        melee = bool(hero.get("melee", False))
        out[hero_id] = {
            "coefficient": COEFF.get(hero_id, 0.9),
            "attack_point": 0.35 if melee else 0.45,
            "backswing": 0.30 if melee else 0.25,
            "innate": {
                "name": innate_name,
                "desc": innate_desc,
                "type": innate_type,
                "value": innate_value,
            },
            "talents": {
                "10": make_talents(hero_id, name, primary, 10),
                "15": make_talents(hero_id, name, primary, 15),
                "20": make_talents(hero_id, name, primary, 20),
            },
        }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(out)} heroes")


if __name__ == "__main__":
    main()
