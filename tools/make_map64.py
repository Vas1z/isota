"""Одноразовый генератор карты 64x64 из старой 48x48-карты."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "map.json"
DST = ROOT / "data" / "map.json"
SCALE = 64.0 / 48.0


def sc(x, y):
    return [round(x * SCALE, 1), round(y * SCALE, 1)]


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    if data.get("river_width") == 1.5:
        print("map is already 64x64; skip")
        return

    data["bases"] = {team: sc(*pos) for team, pos in data["bases"].items()}
    data["spawns"] = {team: sc(*pos) for team, pos in data["spawns"].items()}
    for throne in data["thrones"]:
        throne["pos"] = sc(*throne["pos"])
    for lane, path in data["lanes"].items():
        data["lanes"][lane] = [sc(*p) for p in path]
    for tower in data["towers"]:
        tower["pos"] = sc(*tower["pos"])
    for camp in data["neutrals"]:
        camp["pos"] = sc(*camp["pos"])

    # Четыре новых лесных лагеря: по два на сторону, уникальные типы.
    data["neutrals"].extend([
        {"id": "moss_a", "pos": [22.0, 55.0], "type": "mossback", "count": 2, "respawn": 70},
        {"id": "ember_a", "pos": [46.0, 36.0], "type": "emberling", "count": 3, "respawn": 75},
        {"id": "moss_b", "pos": [9.0, 18.0], "type": "duskbat", "count": 2, "respawn": 70},
        {"id": "ember_b", "pos": [18.0, 9.0], "type": "crystal_golem", "count": 2, "respawn": 75},
    ])

    data["runes"] = [[16.0, 16.0], [32.0, 16.0], [32.0, 48.0], [48.0, 48.0]]
    data["boss"] = {"pos": [32.0, 32.0], "respawn": [480.0, 660.0]}
    data["river_width"] = 1.5

    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {DST}: 64x64, towers={len(data['towers'])}, camps={len(data['neutrals'])}")


if __name__ == "__main__":
    main()
