"""Локальная заглушка матчмейкинга по MMR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

DATA = Path(__file__).resolve().parent.parent / "data" / "mmr.json"


def load_profiles(path: Path = DATA) -> Dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_profiles(profiles: Dict[str, dict], path: Path = DATA) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def ensure_profile(name: str, profiles: Dict[str, dict]) -> dict:
    profile = profiles.setdefault(name, {"mmr": 1000, "wins": 0, "losses": 0})
    return profile


def update_mmr(name: str, won: bool, profiles: Optional[Dict[str, dict]] = None,
               k: int = 32) -> dict:
    profiles = profiles if profiles is not None else load_profiles()
    profile = ensure_profile(name, profiles)
    expected = 1.0 / (1.0 + 10 ** ((1000 - profile["mmr"]) / 400.0))
    score = 1.0 if won else 0.0
    profile["mmr"] = int(round(profile["mmr"] + k * (score - expected)))
    if won:
        profile["wins"] += 1
    else:
        profile["losses"] += 1
    return profile


def find_match(names: List[str], profiles: Optional[Dict[str, dict]] = None,
               max_spread: int = 400) -> dict:
    """Возвращает простую рекомендацию комнаты, не сетевой матчмейкинг."""
    profiles = profiles if profiles is not None else load_profiles()
    ratings = [ensure_profile(name, profiles)["mmr"] for name in names]
    if not ratings:
        return {"ok": False, "reason": "empty", "players": []}
    spread = max(ratings) - min(ratings)
    return {
        "ok": spread <= max_spread,
        "avg_mmr": int(sum(ratings) / len(ratings)),
        "spread": spread,
        "players": list(names),
    }
