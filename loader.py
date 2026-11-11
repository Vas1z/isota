import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load(name: str) -> dict:
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all() -> dict:
    return {
        "settings": load("settings"),
        "controls": load("controls"),
        "hero":     load("hero"),
        "heroes":   load("heroes"),
        "heroes_meta": load("heroes_meta"),
        "items":    load("items"),
        "units":    load("units"),
        "neutrals": load("neutrals"),
        "map":      load("map"),
    }


def validate(data: dict) -> None:
    required = ["settings", "controls", "hero", "units", "map", "heroes", "items", "neutrals"]
    for key in required:
        assert key in data, f"Missing config: {key}"
    assert data["hero"]["team"] in ("A", "B"), "hero.team must be A or B"

    heroes = data["heroes"]["heroes"]
    assert heroes, "heroes.json has no heroes"
    meta = data.get("heroes_meta", {})
    for hero_id, hero in heroes.items():
        assert "base" in hero and "abilities" in hero, f"hero {hero_id}: base/abilities missing"
        assert hero.get("primary") in ("str", "agi", "int"), f"hero {hero_id}: bad primary"
        for key in ("hp", "mana", "damage", "armor", "speed", "atk_range", "atk_cd", "radius",
                    "projectile_speed", "str", "agi", "int"):
            assert key in hero["base"], f"hero {hero_id}: base.{key} missing"
        for ability in hero["abilities"]:
            assert "type" in ability and "name" in ability, f"hero {hero_id}: bad ability"
        if meta:
            assert hero_id in meta, f"hero {hero_id}: heroes_meta missing"
            assert "innate" in meta[hero_id], f"hero {hero_id}: innate missing"
            for level in ("10", "15", "20"):
                assert level in meta[hero_id]["talents"], f"hero {hero_id}: talent {level} missing"
                assert len(meta[hero_id]["talents"][level]) >= 2, f"hero {hero_id}: talent {level} needs 2 choices"

    items = data["items"]["items"]
    assert items, "items.json has no items"
    assert len(items) == 40, f"expected 40 shop items, got {len(items)}"
    for item_id, item in items.items():
        assert "cost" in item and "bonus" in item, f"item {item_id}: cost/bonus missing"
        if item.get("recipe"):
            for component in item["recipe"]:
                assert component in items, f"item {item_id}: unknown component {component}"

    neutrals = data["neutrals"]
    assert neutrals, "neutrals.json has no templates"
    for neutral_id, neutral in neutrals.items():
        for key in ("hp", "speed", "atk_range", "atk_dmg", "atk_cd", "radius"):
            assert key in neutral, f"neutral {neutral_id}: {key} missing"

    lanes = data["map"]["lanes"]
    assert lanes, "map.lanes empty"
    for lane, path in lanes.items():
        assert len(path) >= 2, f"lane {lane} needs >=2 points"
    for t in data["map"]["towers"]:
        assert t["team"] in ("A", "B"), "tower.team must be A or B"
    for t in data["map"].get("thrones", []):
        assert t["team"] in ("A", "B"), "throne.team must be A or B"