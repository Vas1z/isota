"""Smoke-тест предметов: 40 штук, рецепты, активки, продажа, нейтралки."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()
    items = data["items"]["items"]
    assert len(items) == 40
    tiers = {}
    for item in items.values():
        tiers[item.get("tier")] = tiers.get(item.get("tier"), 0) + 1
    assert tiers.get("component") == 10
    assert tiers.get("base") == 10
    assert tiers.get("mid") == 10
    assert tiers.get("top") == 10
    assert len(data["items"]["neutral_items"]) == 6

    # Покупка и авто-рецепт.
    world = World(data)
    hero = world.add_player("p1", "A", hero_id="knight")
    player = world.players["p1"]
    player.unreliable_gold = 5000.0
    player.gold = 5000.0
    player.items.append("short_blade")
    world.apply_command("p1", {"type": "buy", "item": "power_treads"})
    assert "power_treads" in player.items
    assert "short_blade" not in player.items
    assert player.gold < 5000.0

    # Активный предмет.
    world_a = World(data)
    hero_a = world_a.add_player("p1", "A", hero_id="knight")
    pa = world_a.players["p1"]
    pa.unreliable_gold = 5000.0
    pa.gold = 5000.0
    world_a.apply_command("p1", {"type": "buy", "item": "magic_wand"})
    hero_a.hp = hero_a.max_hp * 0.5
    pa.mana = 10.0
    hp_before = hero_a.hp
    mana_before = pa.mana
    world_a.apply_command("p1", {"type": "use_item", "item": "magic_wand"})
    assert hero_a.hp > hp_before and pa.mana > mana_before
    assert pa.item_cooldowns.get("magic_wand", 0) > 0

    # Продажа за 50%.
    world_s = World(data)
    hero_s = world_s.add_player("p1", "A")
    ps = world_s.players["p1"]
    ps.unreliable_gold = 1000.0
    ps.gold = 1000.0
    world_s.apply_command("p1", {"type": "buy", "item": "blade"})
    gold_before = ps.gold
    world_s.apply_command("p1", {"type": "sell", "item": "blade"})
    assert "blade" not in ps.items
    assert ps.gold == gold_before + 225

    # Нейтральный предмет падает после 15 минут.
    world_n = World(data)
    world_n.add_player("p1", "A", hero_id="knight")
    pn = world_n.players["p1"]
    pn.neutral_items.clear()
    world_n.match_time = 1000.0
    for _ in range(200):
        world_n._maybe_drop_neutral_item(pn)
        if pn.neutral_items:
            break
    assert pn.neutral_items, "neutral item did not drop"
    assert pn.neutral_items[0] in data["items"]["neutral_items"]

    print("OK: items 40, recipes, actives, sell, neutral drops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
