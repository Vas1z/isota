"""Авторитетная симуляция мира.

Модуль намеренно не импортирует pygame: его использует и headless-сервер,
и оффлайн-клиент. Всё, что связано с картинкой, вводом и камерой, живёт
в game.py / ui.py.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import math


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------- Юниты ----------
@dataclass
class Unit:
    uid: int
    team: str
    kind: str
    pos: Tuple[float, float]
    hp: float
    max_hp: float
    speed: float = 1.5
    atk_range: float = 1.5
    atk_dmg: float = 10.0
    atk_cd: float = 1.0
    atk_timer: float = 0.0
    radius: float = 0.35
    projectile_speed: float = 8.0
    gold_bounty: int = 0
    armor: float = 0.0
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    wp_index: int = 0
    alive: bool = True
    target: Optional["Unit"] = None
    move_target: Optional[Tuple[float, float]] = None
    attack_target: Optional["Unit"] = None
    last_hit_by: Optional["Unit"] = None
    proj_color: Tuple[int, int, int] = (255, 240, 150)
    owner_player: Optional[str] = None
    death_processed: bool = False

    # ----- обновление -----
    def update(self, dt: float, units: List["Unit"], projectiles: List["Projectile"]) -> None:
        if not self.alive:
            return

        self.atk_timer = max(0.0, self.atk_timer - dt)

        if self.kind == "hero":
            self._update_hero(dt, units, projectiles)
            return

        self.target = self._find_target(units)
        if self.target and dist(self.pos, self.target.pos) <= self.atk_range:
            if self.atk_timer <= 0:
                self._fire(projectiles, self.target)
        elif self.kind != "tower" and self.waypoints and self.wp_index < len(self.waypoints):
            wp = self.waypoints[self.wp_index]
            d = dist(self.pos, wp)
            if d < 0.15:
                self.wp_index += 1
            else:
                self._move_towards(wp, dt)

    def _update_hero(self, dt: float, units: List["Unit"], projectiles: List["Projectile"]) -> None:
        if self.attack_target:
            tgt = self.attack_target
            if not tgt.alive:
                self.attack_target = None
            else:
                d = dist(self.pos, tgt.pos)
                if d <= self.atk_range:
                    self.move_target = None
                    if self.atk_timer <= 0:
                        self._fire(projectiles, tgt)
                else:
                    self._move_towards(tgt.pos, dt)
            return

        if self.move_target:
            d = dist(self.pos, self.move_target)
            if d < 0.1:
                self.move_target = None
            else:
                self._move_towards(self.move_target, dt)

    def _move_towards(self, target: Tuple[float, float], dt: float) -> None:
        d = dist(self.pos, target)
        if d <= 0.0001:
            return
        step = min(self.speed * dt, d)
        self.pos = (
            self.pos[0] + (target[0] - self.pos[0]) / d * step,
            self.pos[1] + (target[1] - self.pos[1]) / d * step,
        )

    def _fire(self, projectiles: List["Projectile"], target: "Unit") -> None:
        self.atk_timer = self.atk_cd
        projectiles.append(Projectile(
            pos=self.pos,
            target=target,
            dmg=self.atk_dmg,
            team=self.team,
            owner=self,
            speed=self.projectile_speed,
            color=self.proj_color,
            radius=8 if self.kind == "tower" else 4,
        ))

    def _find_target(self, units: List["Unit"]) -> Optional["Unit"]:
        best = None
        best_d = self.atk_range + 1.5
        for u in units:
            if u is self or not u.alive or u.team == self.team:
                continue
            d = dist(self.pos, u.pos)
            if d < best_d:
                best_d = d
                best = u
        return best

    # ----- коллизии -----
    def resolve_collision(self, other: "Unit") -> None:
        if self is other or not self.alive or not other.alive:
            return

        d = dist(self.pos, other.pos)
        min_dist = self.radius + other.radius

        if d < min_dist and d > 0.001:
            overlap = min_dist - d
            dx = (self.pos[0] - other.pos[0]) / d
            dy = (self.pos[1] - other.pos[1]) / d

            if self.kind != "tower" and other.kind != "tower":
                self.pos = (self.pos[0] + dx * overlap * 0.5, self.pos[1] + dy * overlap * 0.5)
                other.pos = (other.pos[0] - dx * overlap * 0.5, other.pos[1] - dy * overlap * 0.5)
            elif self.kind != "tower":
                self.pos = (self.pos[0] + dx * overlap, self.pos[1] + dy * overlap)
            elif other.kind != "tower":
                other.pos = (other.pos[0] - dx * overlap, other.pos[1] - dy * overlap)

    # ----- урон -----
    def take_damage(self, dmg: float, attacker: Optional["Unit"] = None) -> None:
        if not self.alive:
            return

        # Простая защита: 6 armor = ~26% снижения урона.
        effective = dmg * (100.0 / (100.0 + max(0.0, self.armor) * 6.0))
        self.hp -= effective

        if attacker:
            self.last_hit_by = attacker

        if self.hp <= 0:
            self.hp = 0
            self.alive = False


@dataclass
class Projectile:
    pos: Tuple[float, float]
    target: Unit
    dmg: float
    team: str
    owner: Unit
    speed: float = 8.0
    alive: bool = True
    color: Tuple[int, int, int] = (255, 240, 150)
    radius: int = 4
    uid: int = 0

    def update(self, dt: float) -> None:
        if not self.alive or not self.target.alive:
            self.alive = False
            return

        d = dist(self.pos, self.target.pos)
        if d < 0.15:
            self.target.take_damage(self.dmg, attacker=self.owner)
            self.alive = False
            return

        step = self.speed * dt
        self.pos = (
            self.pos[0] + (self.target.pos[0] - self.pos[0]) / d * min(step, d),
            self.pos[1] + (self.target.pos[1] - self.pos[1]) / d * min(step, d),
        )


# ---------- Состояние игрока ----------
@dataclass
class PlayerState:
    player_id: str
    team: str
    hero: Unit
    name: str = ""
    slot: int = 0
    gold: float = 0.0
    cs: int = 0
    kills: int = 0
    deaths: int = 0
    respawn_timer: float = 0.0


# ---------- Мир ----------
class World:
    """Серверная/оффлайн-симуляция. Никакого рендера и ввода."""

    def __init__(self, data: dict):
        self.data = data
        self.cfg = data["settings"]
        self.map_cfg = data["map"]
        self.units_cfg = data["units"]
        self.hero_cfg = data["hero"]
        self.colors = {k: tuple(v) for k, v in self.cfg["colors"].items()}

        self.grid_w = self.cfg["grid"]["width"]
        self.grid_h = self.cfg["grid"]["height"]

        self.lanes = {k: [tuple(p) for p in v] for k, v in self.map_cfg["lanes"].items()}
        self.bases = {k: tuple(v) for k, v in self.map_cfg["bases"].items()}
        self.spawns = {
            k: tuple(v)
            for k, v in self.map_cfg.get("spawns", {"A": [4, 20], "B": [20, 4]}).items()
        }

        self.units: List[Unit] = []
        self.projectiles: List[Projectile] = []
        self.players: Dict[str, PlayerState] = {}
        self.events: List[dict] = []

        self.match_time = 0.0
        self.tick_count = 0
        self._next_uid = 1

        self.creep_timer = 0.0
        self.creep_interval = self.cfg["timing"]["creep_interval"]
        self.creeps_per_wave = self.cfg["timing"].get("creeps_per_wave", 5)
        self.respawn_time = self.cfg["timing"].get("respawn_time", 5.0)

        for t in self.map_cfg["towers"]:
            self._add_unit(self._make_tower(t["team"], t["pos"], self.units_cfg["tower"]))

    # ----- сущности -----
    def new_uid(self) -> int:
        uid = self._next_uid
        self._next_uid += 1
        return uid

    def get_unit(self, uid: int) -> Optional[Unit]:
        for u in self.units:
            if u.uid == uid:
                return u
        return None

    def _add_unit(self, unit: Unit) -> Unit:
        if unit.uid == 0:
            unit.uid = self.new_uid()
        self.units.append(unit)
        return unit

    def _make_tower(self, team: str, pos, tpl: dict) -> Unit:
        return Unit(
            uid=0,
            team=team,
            kind="tower",
            pos=tuple(pos),
            hp=tpl["hp"],
            max_hp=tpl["hp"],
            speed=tpl["speed"],
            atk_range=tpl["atk_range"],
            atk_dmg=tpl["atk_dmg"],
            atk_cd=tpl["atk_cd"],
            radius=tpl["radius"],
            projectile_speed=tpl["projectile_speed"],
            gold_bounty=tpl.get("gold_bounty", 0),
            proj_color=(255, 120, 50) if team == "B" else (255, 160, 80),
        )

    def _make_creep(self, team: str, lane_path, tpl: dict, rank: int = 0) -> Unit:
        wps = [(float(x), float(y)) for x, y in lane_path]
        if team == "B":
            wps = list(reversed(wps))

        start = list(wps[0])
        if rank > 0 and len(wps) > 1:
            dx = wps[0][0] - wps[1][0]
            dy = wps[0][1] - wps[1][1]
            length = math.hypot(dx, dy)
            if length > 0:
                offset = 0.35 * rank
                start[0] += (dx / length) * offset
                start[1] += (dy / length) * offset

        return Unit(
            uid=0,
            team=team,
            kind="creep",
            pos=tuple(start),
            hp=tpl["hp"],
            max_hp=tpl["hp"],
            speed=tpl["speed"],
            atk_range=tpl["atk_range"],
            atk_dmg=tpl["atk_dmg"],
            atk_cd=tpl["atk_cd"],
            radius=tpl["radius"],
            projectile_speed=tpl["projectile_speed"],
            gold_bounty=tpl.get("gold_bounty", 0),
            waypoints=wps,
            wp_index=1,
            proj_color=(255, 240, 150),
        )

    def _spawn_pos(self, team: str, slot: int) -> Tuple[float, float]:
        base = self.spawns.get(team, self.bases.get(team, (2.0, 2.0)))
        return (base[0] + 0.8 * slot, base[1])

    # ----- игроки -----
    def add_player(self, player_id: str, team: str, name: str = "") -> Unit:
        if player_id in self.players:
            return self.players[player_id].hero

        slot = sum(1 for p in self.players.values() if p.team == team)
        spawn = self._spawn_pos(team, slot)
        s = self.hero_cfg["stats"]

        hero = Unit(
            uid=0,
            team=team,
            kind="hero",
            pos=spawn,
            hp=s["hp"],
            max_hp=s["hp"],
            speed=s["speed"],
            atk_range=s["atk_range"],
            atk_dmg=s["atk_dmg"],
            atk_cd=s["atk_cd"],
            radius=s["radius"],
            projectile_speed=s["projectile_speed"],
            armor=s.get("armor", 0),
            proj_color=self.colors.get("projectile", (255, 240, 150)),
            owner_player=player_id,
        )
        self._add_unit(hero)

        self.players[player_id] = PlayerState(
            player_id=player_id,
            team=team,
            hero=hero,
            name=name,
            slot=slot,
        )
        return hero

    def remove_player(self, player_id: str) -> None:
        player = self.players.pop(player_id, None)
        if not player:
            return
        hero = player.hero
        hero.alive = False
        self.units = [u for u in self.units if u is not hero]

    # ----- команды -----
    def apply_command(self, player_id: str, cmd: dict) -> None:
        player = self.players.get(player_id)
        if not player or not cmd or not isinstance(cmd, dict):
            return

        hero = player.hero
        if not hero or not hero.alive:
            return

        ctype = cmd.get("type")

        if ctype == "move":
            try:
                x = max(0.0, min(float(self.grid_w), float(cmd["x"])))
                y = max(0.0, min(float(self.grid_h), float(cmd["y"])))
            except (KeyError, TypeError, ValueError):
                return
            hero.move_target = (x, y)
            hero.attack_target = None

        elif ctype == "attack":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                return
            if target and target.alive and target.team != hero.team:
                hero.attack_target = target
                hero.move_target = None

        elif ctype == "stop":
            hero.move_target = None
            hero.attack_target = None

    # ----- тик -----
    def tick(self, dt: float) -> None:
        dt = max(0.0, min(dt, 0.1))
        self.match_time += dt
        self.tick_count += 1

        # Пассивное золото.
        for player in self.players.values():
            player.gold += dt

        # Волны крипов.
        self.creep_timer += dt
        while self.creep_timer >= self.creep_interval:
            self.creep_timer -= self.creep_interval
            self._spawn_creep_wave()

        # Юниты.
        for unit in list(self.units):
            if unit.alive:
                unit.update(dt, self.units, self.projectiles)

        # Проектилям нужен uid для снапшотов.
        for proj in self.projectiles:
            if proj.uid == 0:
                proj.uid = self.new_uid()

        # Коллизии.
        for i in range(len(self.units)):
            for j in range(i + 1, len(self.units)):
                u1 = self.units[i]
                u2 = self.units[j]
                if u1.alive and u2.alive and dist(u1.pos, u2.pos) < (u1.radius + u2.radius):
                    u1.resolve_collision(u2)

        # Снаряды.
        for proj in self.projectiles:
            proj.update(dt)
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Смерти, награды и статистика.
        for unit in self.units:
            if unit.alive or unit.death_processed:
                continue
            unit.death_processed = True

            if unit.kind == "hero":
                self._on_hero_death(unit)
            elif unit.gold_bounty > 0:
                self._on_unit_death(unit)

        # Респавн героев.
        self._update_respawns(dt)

        # Убираем мёртвых не-героев; мёртвые герои остаются для респавна.
        self.units = [u for u in self.units if u.alive or u.kind == "hero"]

    def _spawn_creep_wave(self) -> None:
        for lane_name in self.lanes:
            path = self.lanes[lane_name]
            for team in ("A", "B"):
                for i in range(self.creeps_per_wave):
                    self._add_unit(self._make_creep(team, path, self.units_cfg["creep"], rank=i))

    def _on_hero_death(self, unit: Unit) -> None:
        player = self.players.get(unit.owner_player)
        if not player:
            return

        player.deaths += 1
        player.respawn_timer = self.respawn_time

        killer = unit.last_hit_by
        if killer and killer.owner_player in self.players:
            if killer.owner_player != unit.owner_player:
                self.players[killer.owner_player].kills += 1

        self.events.append({
            "kind": "hero_death",
            "player": unit.owner_player,
            "killer": killer.owner_player if killer else None,
            "x": unit.pos[0],
            "y": unit.pos[1],
            "respawn": player.respawn_timer,
        })

    def _on_unit_death(self, unit: Unit) -> None:
        killer = unit.last_hit_by
        if killer and killer.owner_player in self.players:
            player = self.players[killer.owner_player]
            player.gold += unit.gold_bounty
            player.cs += 1
            self.events.append({
                "kind": "bounty",
                "player": player.player_id,
                "unit": unit.uid,
                "amount": unit.gold_bounty,
                "x": unit.pos[0],
                "y": unit.pos[1],
            })
        unit.gold_bounty = 0

    def _update_respawns(self, dt: float) -> None:
        for player in self.players.values():
            hero = player.hero
            if hero.alive:
                continue

            player.respawn_timer = max(0.0, player.respawn_timer - dt)
            if player.respawn_timer > 0:
                continue

            hero.alive = True
            hero.hp = hero.max_hp
            hero.pos = self._spawn_pos(player.team, player.slot)
            hero.move_target = None
            hero.attack_target = None
            hero.last_hit_by = None
            hero.atk_timer = 0.0
            hero.death_processed = False

            self.events.append({
                "kind": "respawn",
                "player": player.player_id,
                "x": hero.pos[0],
                "y": hero.pos[1],
            })

    # ----- снапшот для клиента -----
    def snapshot(self) -> dict:
        units = []
        for u in self.units:
            entry = {
                "id": u.uid,
                "kind": u.kind,
                "team": u.team,
                "x": round(u.pos[0], 3),
                "y": round(u.pos[1], 3),
                "hp": round(u.hp, 1),
                "max_hp": round(u.max_hp, 1),
                "radius": u.radius,
                "range": u.atk_range,
                "alive": u.alive,
            }
            if u.kind == "hero":
                entry.update({
                    "dmg": round(u.atk_dmg, 1),
                    "speed": u.speed,
                    "armor": u.armor,
                })
            units.append(entry)

        projectiles = [
            {
                "id": p.uid,
                "x": round(p.pos[0], 3),
                "y": round(p.pos[1], 3),
                "r": p.radius,
                "color": list(p.color),
            }
            for p in self.projectiles
        ]

        players = {
            pid: {
                "team": p.team,
                "name": p.name,
                "gold": int(p.gold),
                "cs": p.cs,
                "kills": p.kills,
                "deaths": p.deaths,
                "respawn": round(p.respawn_timer, 2),
                "hero": p.hero.uid if p.hero else None,
            }
            for pid, p in self.players.items()
        }

        return {
            "tick": self.tick_count,
            "time": round(self.match_time, 3),
            "units": units,
            "projectiles": projectiles,
            "players": players,
        }
