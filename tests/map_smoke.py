"""Smoke-тест карты 64x64, лагерей, рун и босса."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import loader  # noqa: E402
from shared.sim import World  # noqa: E402


def main() -> int:
    data = loader.load_all()
    loader.validate(data)
    assert data["settings"]["grid"]["width"] == 64
    assert data["settings"]["grid"]["height"] == 64
    assert set(data["map"]["lanes"]) == {"top", "mid", "bot"}
    assert len(data["map"]["towers"]) == 22
    assert len(data["map"]["thrones"]) == 2
    assert len(data["map"]["neutrals"]) == 12
    assert len(data["map"]["runes"]) == 4
    assert "boss" in data["map"]

    new_types = {"mossback", "emberling", "duskbat", "crystal_golem"}
    assert new_types <= set(data["neutrals"])

    world = World(data)
    world.add_player("p1", "A", hero_id="knight")
    assert len(world.runes) == 4
    assert {r["kind"] for r in world.runes} == {"wealth", "wisdom"}
    assert world.boss is not None and world.boss.is_boss
    assert sum(1 for u in world.units if u.kind == "courier") == 1
    assert world.camps and len(world.camps) == 12
    print("OK: map64, jungle, runes, boss and courier spawned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
