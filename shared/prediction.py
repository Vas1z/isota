"""Клиентское предсказание движения и история для лаг-компенсации."""

from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, Optional, Tuple

Vec = Tuple[float, float]


def predict_position(pos: Vec, target: Vec, speed: float, dt: float) -> Vec:
    dx = target[0] - pos[0]
    dy = target[1] - pos[1]
    d = math.hypot(dx, dy)
    if d <= 0.0001:
        return pos
    step = min(speed * dt, d)
    return (pos[0] + dx / d * step, pos[1] + dy / d * step)


class LagCompensator:
    """Кольцевой буфер позиций юнитов по тикам сервера."""

    def __init__(self, max_ticks: int = 60):
        self.max_ticks = max_ticks
        self.history: Deque[Tuple[int, Dict[int, Vec]]] = deque(maxlen=max_ticks)

    def record(self, tick: int, units) -> None:
        snapshot = {
            int(u.uid): (float(u.pos[0]), float(u.pos[1]))
            for u in units
        }
        self.history.append((int(tick), snapshot))

    def position_at(self, uid: int, tick: int) -> Optional[Vec]:
        best = None
        for recorded_tick, positions in self.history:
            if uid not in positions:
                continue
            if recorded_tick <= tick:
                best = positions[uid]
            else:
                return best if best is not None else positions[uid]
        return best

    def nearest(self, uid: int, tick: int) -> Optional[Vec]:
        if not self.history:
            return None
        return self.position_at(uid, tick)
