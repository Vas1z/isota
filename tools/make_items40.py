"""Собирает data/items.json: 40 магазинных предметов + нейтральные тиры."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "items.json"


def item(name, cost, desc, icon, bonus, tier, recipe=None, **extra):
    data = {
        "name": name,
        "cost": cost,
        "desc": desc,
        "icon": f"assets/items/{icon}.png",
        "bonus": bonus,
        "tier": tier,
    }
    if recipe:
        data["recipe"] = recipe
    data.update(extra)
    return data


def main() -> None:
    items = {}

    # 10 компонентов.
    items.update({
        "twig": item("Ветка", 50, "+1 ко всем атрибутам", "ring", {"str": 1, "agi": 1, "int": 1}, "component"),
        "leather": item("Лоскут кожи", 90, "+70 к максимальному HP", "armor", {"hp": 70}, "component"),
        "mote": item("Пылинка маны", 80, "+60 к максимальной мане", "mana_crystal", {"mana": 60}, "component"),
        "short_blade": item("Короткий клинок", 120, "+8 к урону", "blade", {"damage": 8}, "component"),
        "buckler": item("Малый щит", 110, "+2 к броне", "armor", {"armor": 2}, "component"),
        "robe": item("Ученическая роба", 100, "+8% сопротивления магии", "cloak", {"magic_resist": 0.08}, "component"),
        "feather": item("Быстрое перо", 100, "+0.12 к скорости", "boots", {"speed": 0.12}, "component"),
        "seed": item("Семя жизни", 130, "+90 к максимальному HP", "heart", {"hp": 90}, "component"),
        "charm": item("Оберег фокуса", 120, "+40 к максимальной мане", "ring", {"mana": 40}, "component"),
        "scroll": item("Свиток рецепта", 150, "+5 к урону", "staff", {"damage": 5}, "component"),
    })

    # 10 базовых.
    items.update({
        "boots": item("Ботинки", 250, "+0.35 к скорости передвижения", "boots", {"speed": 0.35}, "base", unique=True),
        "blade": item("Клинок", 450, "+12 к урону", "blade", {"damage": 12}, "base"),
        "armor": item("Латы", 400, "+6 к броне", "armor", {"armor": 6}, "base"),
        "mana_crystal": item("Кристалл маны", 300, "+120 к максимальной мане", "mana_crystal", {"mana": 120}, "base"),
        "heart": item("Сердце", 600, "+150 к максимальному HP", "heart", {"hp": 150}, "base"),
        "ring": item("Кольцо оберега", 350, "+3 к броне, +40 к HP", "ring", {"armor": 3, "hp": 40}, "base", unique=True),
        "cloak": item("Плащ пепельной тени", 500, "+2 к броне, +0.12 к скорости", "cloak", {"armor": 2, "speed": 0.12}, "base", unique=True),
        "staff": item("Посох ржавых звёзд", 650, "+150 к мане, +15 к урону", "staff", {"mana": 150, "damage": 15}, "base"),
        "orb": item("Сфера гнилого света", 700, "+22 к урону", "orb", {"damage": 22}, "base", unique=True),
        "greaves": item("Путники болот", 550, "+0.3 к скорости, +2 к броне", "greaves", {"speed": 0.3, "armor": 2}, "base", unique=True),
    })

    # 10 средних.
    items.update({
        "power_treads": item("Шаги силы", 950, "+0.45 скорости, +18 урона", "boots",
                             {"speed": 0.45, "damage": 18}, "mid",
                             recipe=["boots", "short_blade"], unique=True),
        "magic_wand": item("Жезл искр", 700, "+3 атрибута, +80 маны", "staff",
                           {"str": 3, "agi": 3, "int": 3, "mana": 80}, "mid",
                           recipe=["twig", "charm", "mote"], unique=True,
                           active={"name": "Вспышка", "key": 1, "cooldown": 15, "mana": 0,
                                   "effect": "restore", "hp": 80, "mana_restore": 80}),
        "phase_boots": item("Фазовые шаги", 900, "+0.5 скорости, +8 брони", "boots",
                            {"speed": 0.5, "armor": 8}, "mid",
                            recipe=["boots", "feather"], unique=True),
        "bracer": item("Наруч", 700, "+5 силы, +100 HP", "ring",
                       {"str": 5, "hp": 100}, "mid", recipe=["twig", "buckler"]),
        "null_talisman": item("Пустой талисман", 700, "+5 интеллекта, +100 маны", "mana_crystal",
                              {"int": 5, "mana": 100}, "mid", recipe=["robe", "mote"]),
        "wraith_band": item("Призрачный браслет", 700, "+5 ловкости, +8 урона", "ring",
                            {"agi": 5, "damage": 8}, "mid", recipe=["leather", "short_blade"]),
        "soul_ring": item("Кольцо душ", 800, "+4 брони, +120 маны", "ring",
                          {"armor": 4, "mana": 120}, "mid", recipe=["ring", "mote"], unique=True,
                          active={"name": "Обмен", "key": 2, "cooldown": 25, "mana": 0,
                                  "effect": "blood_mana", "hp_cost": 100, "mana_restore": 150}),
        "iron_helm": item("Железный шлем", 850, "+9 брони, +100 HP", "armor",
                          {"armor": 9, "hp": 100}, "mid", recipe=["armor", "buckler"]),
        "void_stone": item("Камень пустоты", 800, "+180 маны, +10 урона", "mana_crystal",
                           {"mana": 180, "damage": 10}, "mid", recipe=["mana_crystal", "mote"]),
        "echo_blade": item("Клинок эха", 950, "+25 урона, +10% скорости атаки", "blade",
                           {"damage": 25, "attack_speed": 0.10}, "mid",
                           recipe=["blade", "short_blade"], unique=True,
                           orb={"type": "chain", "chance": 0.25, "damage": 50, "jumps": 3}),
    })

    # 10 топовых.
    items.update({
        "adamant_core": item("Адамантовое ядро", 3600, "+220 HP, +12 брони, актив: иммунитет к магии", "armor",
                             {"hp": 220, "armor": 12}, "top",
                             recipe=["iron_helm", "robe", "scroll"], unique=True,
                             active={"name": "Адамант", "key": 3, "cooldown": 70, "mana": 0,
                                     "effect": "magic_immune", "duration": 5}),
        "phase_dagger": item("Фазовый кинжал", 2250, "+15 урона, актив: рывок", "blade",
                             {"damage": 15}, "top", recipe=["short_blade", "staff"], unique=True,
                             active={"name": "Рывок", "key": 4, "cooldown": 18, "mana": 0,
                                     "effect": "blink", "range": 6}),
        "sunder_blade": item("Клинок разлома", 4100, "+55 урона, орб: снижение брони", "blade",
                             {"damage": 55}, "top", recipe=["orb", "blade", "short_blade"], unique=True,
                             orb={"type": "armor_break", "value": 5, "duration": 4}),
        "bloodheart": item("Кровавое сердце", 4300, "+600 HP, +35 урона, вампиризм 20%", "heart",
                           {"hp": 600, "damage": 35, "lifesteal": 0.20}, "top",
                           recipe=["heart", "orb"], unique=True),
        "evasion_fan": item("Веер уклонения", 3800, "+30% уклонения, +25 скорости атаки", "cloak",
                            {"evasion": 0.30, "attack_speed": 0.25}, "top",
                            recipe=["feather", "cloak", "feather"], unique=True),
        "sunfire_relic": item("Реликвия солнца", 4000, "+50 урона, аура: 40 маг. урона/сек", "orb",
                              {"damage": 50, "burn_aura": 40}, "top",
                              recipe=["staff", "orb", "scroll"], unique=True),
        "hex_rod": item("Жезл превращения", 4200, "+25 инт, актив: сайленс и рут", "staff",
                        {"int": 25}, "top", recipe=["staff", "charm", "scroll"], unique=True,
                        active={"name": "Превращение", "key": 5, "cooldown": 30, "mana": 100,
                                "effect": "hex", "duration": 3.0, "range": 5}),
        "frost_guard": item("Морозный страж", 4000, "+15 брони, актив: замедление по области", "armor",
                            {"armor": 15, "mana": 100}, "top",
                            recipe=["armor", "mana_crystal", "cloak"], unique=True,
                            active={"name": "Мороз", "key": 6, "cooldown": 35, "mana": 80,
                                    "effect": "frost_nova", "radius": 4, "slow": 0.45, "duration": 3}),
        "agha_core": item("Ядро Аганима", 4200, "Усиливает ультимейт; максимум 2 на команду", "staff",
                          {}, "top", unique=True, team_limit=2, agha=True),
        "shard": item("Осколок", 1400, "Усиливает базовую способность; максимум 2 на команду", "mana_crystal",
                      {}, "top", unique=True, team_limit=2, shard=True),
    })

    neutral = {
        "moss_charm": item("Мшистый оберег", 0, "Нейтральный тир 1: +40 HP, +1 броня", "ring",
                           {"hp": 40, "armor": 1}, "neutral", neutral_tier=1),
        "spark_orb": item("Искровая сфера", 0, "Нейтральный тир 1: +6 урона", "orb",
                          {"damage": 6}, "neutral", neutral_tier=1),
        "dusk_veil": item("Покров сумерек", 0, "Нейтральный тир 2: +10% уклонения", "cloak",
                          {"evasion": 0.10}, "neutral", neutral_tier=2),
        "ember_heart": item("Угольное сердце", 0, "Нейтральный тир 2: +120 HP", "heart",
                            {"hp": 120}, "neutral", neutral_tier=2),
        "river_eye": item("Око омута", 0, "Нейтральный тир 3: +15% маг. резиста", "mana_crystal",
                          {"magic_resist": 0.15}, "neutral", neutral_tier=3),
        "titan_seal": item("Печать титана", 0, "Нейтральный тир 3: +20 урона, +6 брони", "armor",
                           {"damage": 20, "armor": 6}, "neutral", neutral_tier=3),
    }

    assert len(items) == 40, len(items)
    OUT.write_text(json.dumps({"items": items, "neutral_items": neutral},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(items)} shop items, {len(neutral)} neutral items")


if __name__ == "__main__":
    main()
