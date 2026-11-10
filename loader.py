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
        "units":    load("units"),
        "map":      load("map"),
    }


def validate(data: dict) -> None:
    required = ["settings", "controls", "hero", "units", "map"]
    for key in required:
        assert key in data, f"Missing config: {key}"
    assert data["hero"]["team"] in ("A", "B"), "hero.team must be A or B"
    lanes = data["map"]["lanes"]
    assert lanes, "map.lanes empty"
    for lane, path in lanes.items():
        assert len(path) >= 2, f"lane {lane} needs >=2 points"
    for t in data["map"]["towers"]:
        assert t["team"] in ("A", "B"), "tower.team must be A or B"