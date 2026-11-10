#!/usr/bin/env python3
"""Проверка большой карты 48x48 для 2D MOBA-прототипа.

Использование:
    python tools/validate_map.py [path/to/map_large.json]

Скрипт проверяет структуру JSON, границы сетки, линии, вышки, троны,
базы, спавны, нейтральные лагеря и руны. При успехе печатает OK.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

GRID_SIZE = 48.0
HALF_GRID = GRID_SIZE / 2.0
LANE_NAMES = ("top", "mid", "bot")
TEAMS = ("A", "B")
TOWERS_PER_TEAM = 11
MIN_CAMPS = 6
CAMP_TYPES = frozenset({"wolf", "golem", "troll"})

# Вышки стоят вдоль линии, но не на самом пути крипов.
TOWER_LANE_MIN = 0.8
TOWER_LANE_MAX = 4.0
# Лагеря не должны стоять на линии или вплотную к вышке.
CAMP_LANE_MIN = 2.5
CAMP_TOWER_MIN = 2.0
# Допуск для "линия начинается/заканчивается у базы" и трона у базы.
BASE_TOLERANCE = 3.0

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "data" / "map_large.json"

Point = Tuple[float, float]


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def parse_point(value, where: str) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        fail(f"{where}: expected [x, y], got {value!r}")

    x, y = value
    for name, coord in (("x", x), ("y", y)):
        if isinstance(coord, bool) or not isinstance(coord, (int, float)):
            fail(f"{where}: {name} must be a number, got {coord!r}")
        if not math.isfinite(float(coord)):
            fail(f"{where}: {name} must be finite")
        if not 0.0 <= float(coord) <= GRID_SIZE:
            fail(f"{where}: {name}={coord} outside [0, {GRID_SIZE:g}]")

    return float(x), float(y)


def parse_points(value, where: str) -> List[Point]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        fail(f"{where}: expected a list of at least 2 points")
    return [parse_point(p, f"{where}[{i}]") for i, p in enumerate(value)]


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_segment_dist(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def lane_distance(p: Point, lanes: Dict[str, Sequence[Point]]) -> float:
    best = math.inf
    for pts in lanes.values():
        for a, b in zip(pts, pts[1:]):
            best = min(best, point_segment_dist(p, a, b))
    return best


def validate_bases(data: dict) -> Dict[str, Point]:
    bases_raw = data.get("bases")
    if not isinstance(bases_raw, dict):
        fail("bases: object with teams A and B expected")

    bases: Dict[str, Point] = {}
    for team in TEAMS:
        if team not in bases_raw:
            fail(f"bases: missing team {team}")
        bases[team] = parse_point(bases_raw[team], f"bases.{team}")

    a, b = bases["A"], bases["B"]
    if not (a[0] < HALF_GRID and a[1] > HALF_GRID):
        fail(f"bases.A: expected bottom-left corner, got {list(a)}")
    if not (b[0] > HALF_GRID and b[1] < HALF_GRID):
        fail(f"bases.B: expected top-right corner, got {list(b)}")
    return bases


def validate_spawns(data: dict, bases: Dict[str, Point]) -> Dict[str, Point]:
    spawns_raw = data.get("spawns")
    if not isinstance(spawns_raw, dict):
        fail("spawns: object with teams A and B expected")

    spawns: Dict[str, Point] = {}
    for team in TEAMS:
        if team not in spawns_raw:
            fail(f"spawns: missing team {team}")
        spawn = parse_point(spawns_raw[team], f"spawns.{team}")
        if dist(spawn, bases[team]) > 6.0:
            fail(f"spawns.{team}: too far from base ({dist(spawn, bases[team]):.2f})")
        spawns[team] = spawn
    return spawns


def validate_thrones(data: dict, bases: Dict[str, Point]) -> Dict[str, Point]:
    thrones_raw = data.get("thrones")
    if not isinstance(thrones_raw, list):
        fail("thrones: list expected")
    if len(thrones_raw) != 2:
        fail(f"thrones: expected exactly 2, got {len(thrones_raw)}")

    thrones: Dict[str, Point] = {}
    for i, throne in enumerate(thrones_raw):
        if not isinstance(throne, dict):
            fail(f"thrones[{i}]: object expected")
        team = throne.get("team")
        if team not in TEAMS:
            fail(f"thrones[{i}].team: expected A or B, got {team!r}")
        if team in thrones:
            fail(f"thrones: duplicate throne for team {team}")
        pos = parse_point(throne.get("pos"), f"thrones[{i}].pos")
        if dist(pos, bases[team]) > BASE_TOLERANCE:
            fail(
                f"thrones[{i}]: throne of team {team} is not at its base "
                f"({dist(pos, bases[team]):.2f} > {BASE_TOLERANCE})"
            )
        thrones[team] = pos

    return thrones


def validate_lanes(data: dict, bases: Dict[str, Point]) -> Dict[str, List[Point]]:
    lanes_raw = data.get("lanes")
    if not isinstance(lanes_raw, dict):
        fail("lanes: object expected")

    lanes: Dict[str, List[Point]] = {}
    for name in LANE_NAMES:
        if name not in lanes_raw:
            fail(f"lanes: missing '{name}' lane")
        lanes[name] = parse_points(lanes_raw[name], f"lanes.{name}")

        start, end = lanes[name][0], lanes[name][-1]
        if dist(start, bases["A"]) > BASE_TOLERANCE:
            fail(
                f"lanes.{name}: must start near base A, "
                f"got {list(start)} (dist {dist(start, bases['A']):.2f})"
            )
        if dist(end, bases["B"]) > BASE_TOLERANCE:
            fail(
                f"lanes.{name}: must end near base B, "
                f"got {list(end)} (dist {dist(end, bases['B']):.2f})"
            )

    return lanes


def validate_towers(data: dict, lanes: Dict[str, Sequence[Point]]) -> List[Point]:
    towers_raw = data.get("towers")
    if not isinstance(towers_raw, list):
        fail("towers: list expected")

    seen = set()
    counts = {team: 0 for team in TEAMS}
    positions: List[Point] = []

    for i, tower in enumerate(towers_raw):
        if not isinstance(tower, dict):
            fail(f"towers[{i}]: object expected")
        team = tower.get("team")
        if team not in TEAMS:
            fail(f"towers[{i}].team: expected A or B, got {team!r}")

        pos = parse_point(tower.get("pos"), f"towers[{i}].pos")
        key = (round(pos[0], 3), round(pos[1], 3))
        if key in seen:
            fail(f"towers[{i}]: duplicate tower at {list(pos)}")
        seen.add(key)

        d = lane_distance(pos, lanes)
        if d < TOWER_LANE_MIN:
            fail(
                f"towers[{i}] ({team}) at {list(pos)}: stands on the lane path "
                f"(distance {d:.2f} < {TOWER_LANE_MIN})"
            )
        if d > TOWER_LANE_MAX:
            fail(
                f"towers[{i}] ({team}) at {list(pos)}: too far from any lane "
                f"(distance {d:.2f} > {TOWER_LANE_MAX})"
            )

        counts[team] += 1
        positions.append(pos)

    if len(towers_raw) != TOWERS_PER_TEAM * len(TEAMS):
        fail(
            f"towers: expected {TOWERS_PER_TEAM * len(TEAMS)} total, "
            f"got {len(towers_raw)}"
        )
    for team in TEAMS:
        if counts[team] != TOWERS_PER_TEAM:
            fail(f"towers: team {team} has {counts[team]}, expected {TOWERS_PER_TEAM}")

    return positions


def validate_neutrals(
    data: dict,
    lanes: Dict[str, Sequence[Point]],
    towers: Sequence[Point],
) -> List[dict]:
    neutrals = data.get("neutrals")
    if not isinstance(neutrals, list):
        fail("neutrals: list expected")
    if len(neutrals) < MIN_CAMPS:
        fail(f"neutrals: expected at least {MIN_CAMPS} camps, got {len(neutrals)}")

    seen_ids = set()
    sides = {"A": False, "B": False}

    for i, camp in enumerate(neutrals):
        if not isinstance(camp, dict):
            fail(f"neutrals[{i}]: object expected")

        camp_id = camp.get("id")
        if not isinstance(camp_id, str) or not camp_id.strip():
            fail(f"neutrals[{i}].id: non-empty string expected")
        if camp_id in seen_ids:
            fail(f"neutrals[{i}].id: duplicate id {camp_id!r}")
        seen_ids.add(camp_id)

        pos = parse_point(camp.get("pos"), f"neutrals[{i}].pos")

        camp_type = camp.get("type")
        if not isinstance(camp_type, str) or camp_type not in CAMP_TYPES:
            fail(
                f"neutrals[{i}].type: expected one of {sorted(CAMP_TYPES)}, "
                f"got {camp_type!r}"
            )

        count = camp.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 4:
            fail(f"neutrals[{i}].count: integer in [2, 4] expected, got {count!r}")

        respawn = camp.get("respawn")
        if isinstance(respawn, bool) or not isinstance(respawn, (int, float)):
            fail(f"neutrals[{i}].respawn: number expected, got {respawn!r}")
        if float(respawn) != 60.0:
            fail(f"neutrals[{i}].respawn: expected 60, got {respawn!r}")

        d_lane = lane_distance(pos, lanes)
        if d_lane < CAMP_LANE_MIN:
            fail(
                f"neutrals[{i}] ({camp_id}) at {list(pos)}: too close to a lane "
                f"(distance {d_lane:.2f} < {CAMP_LANE_MIN})"
            )

        if towers:
            d_tower = min(dist(pos, tower) for tower in towers)
            if d_tower < CAMP_TOWER_MIN:
                fail(
                    f"neutrals[{i}] ({camp_id}) at {list(pos)}: too close to a tower "
                    f"(distance {d_tower:.2f} < {CAMP_TOWER_MIN})"
                )

        if pos[1] - pos[0] >= 2.0:
            sides["A"] = True
        elif pos[0] - pos[1] >= 2.0:
            sides["B"] = True
        else:
            fail(
                f"neutrals[{i}] ({camp_id}) at {list(pos)}: camp must be in the "
                f"jungle, not on the river x=y"
            )

    if not all(sides.values()):
        fail("neutrals: camps must be present on both sides of the river x=y")

    return neutrals


def validate_runes(data: dict) -> List[Point]:
    runes_raw = data.get("runes")
    if not isinstance(runes_raw, list):
        fail("runes: list expected")
    if len(runes_raw) != 2:
        fail(f"runes: expected exactly 2, got {len(runes_raw)}")

    runes = [parse_point(r, f"runes[{i}]") for i, r in enumerate(runes_raw)]
    if len({(round(x, 3), round(y, 3)) for x, y in runes}) != 2:
        fail("runes: duplicate rune positions")

    for i, rune in enumerate(runes):
        if abs(rune[0] - rune[1]) > 3.0:
            fail(
                f"runes[{i}] at {list(rune)}: rune must be on or near the river x=y"
            )

    return runes


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        fail("root: JSON object expected")

    for key in ("bases", "spawns", "thrones", "lanes", "towers", "neutrals", "runes"):
        if key not in data:
            fail(f"root: missing '{key}'")

    bases = validate_bases(data)
    validate_spawns(data, bases)
    thrones = validate_thrones(data, bases)
    lanes = validate_lanes(data, bases)
    towers = validate_towers(data, lanes)
    neutrals = validate_neutrals(data, lanes, towers)
    runes = validate_runes(data)

    return {
        "bases": bases,
        "thrones": thrones,
        "lanes": lanes,
        "towers": towers,
        "neutrals": neutrals,
        "runes": runes,
    }


def main(argv: List[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_MAP

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"FAIL: map file not found: {path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON in {path}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"FAIL: cannot read {path}: {exc}", file=sys.stderr)
        return 1

    try:
        info = validate(data)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    tower_counts = {team: 0 for team in TEAMS}
    for tower in data["towers"]:
        tower_counts[tower["team"]] += 1

    print("OK")
    print(f"map: {path}")
    print(f"grid: {GRID_SIZE:g}x{GRID_SIZE:g}")
    print(f"lanes: {', '.join(info['lanes'])}")
    print(
        "towers: {} (A={}, B={})".format(
            len(info["towers"]), tower_counts["A"], tower_counts["B"]
        )
    )
    print(f"thrones: {len(info['thrones'])}")
    print(f"neutrals: {len(info['neutrals'])} camps")
    print(f"runes: {len(info['runes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
