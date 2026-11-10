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
    melee: bool = False
    atk_dmg: float = 10.0
    atk_cd: float = 1.0
    atk_timer: float = 0.0
    radius: float = 0.35
    projectile_speed: float = 8.0
    gold_bounty: int = 0
    xp_bounty: int = 0
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
    speed_mult: float = 1.0
    speed_buff_timer: float = 0.0
    slow_mult: float = 1.0
    slow_timer: float = 0.0
    stun_timer: float = 0.0
    damage_contributors: set = field(default_factory=set)
    prev_pos: Optional[Tuple[float, float]] = None
    stuck_timer: float = 0.0
    home_pos: Optional[Tuple[float, float]] = None
    leash_range: float = 7.0
    camp_id: Optional[str] = None
    neutral_type: str = ""
    respawn_time: float = 60.0

    # ----- обновление -----
    def update(self, dt: float, units: List["Unit"], projectiles: List["Projectile"],
               events: Optional[List[dict]] = None) -> None:
        if not self.alive:
            return

        # Трон — статичная цель, которая не двигается и не атакует.
        if self.kind == "throne":
            return

        self.atk_timer = max(0.0, self.atk_timer - dt)

        self.speed_buff_timer = max(0.0, self.speed_buff_timer - dt)
        if self.speed_buff_timer <= 0:
            self.speed_mult = 1.0

        self.slow_timer = max(0.0, self.slow_timer - dt)
        if self.slow_timer <= 0:
            self.slow_mult = 1.0

        self.stun_timer = max(0.0, self.stun_timer - dt)
        if self.stun_timer > 0:
            return

        if self.kind == "hero":
            self._update_hero(dt, units, projectiles, events)
            return

        if self.kind == "neutral":
            self._update_neutral(dt, units, projectiles, events)
            return

        moved_last_tick = 0.0
        if self.kind in ("creep", "creep_ranged"):
            if self.prev_pos is None:
                self.prev_pos = self.pos
            moved_last_tick = dist(self.pos, self.prev_pos)
            self.prev_pos = self.pos

        self.target = self._find_target(units)

        if self.target and dist(self.pos, self.target.pos) <= self.atk_range:
            self.stuck_timer = 0.0
            if self.atk_timer <= 0:
                self._fire(projectiles, self.target, events)
        elif (
            self.kind != "tower"
            and self.target
            and self.target.kind in ("tower", "throne")
            and dist(self.pos, self.target.pos) <= self.atk_range + 0.8
        ):
            # Не стоять перед вышкой: подойти на дистанцию удара.
            self.stuck_timer = 0.0
            self._move_towards(self.target.pos, dt)
        elif self.kind != "tower" and self.waypoints and self.wp_index < len(self.waypoints):
            wp = self.waypoints[self.wp_index]
            d = dist(self.pos, wp)
            if d < 0.15:
                self.wp_index += 1
                self.stuck_timer = 0.0
            else:
                self._move_towards(wp, dt)
                if moved_last_tick < 0.008:
                    self.stuck_timer += dt
                    if self.stuck_timer >= 0.6 and self.wp_index < len(self.waypoints) - 1:
                        # Мягкий анти-стак: пропускаем точку, если реально застряли.
                        self.wp_index += 1
                        self.stuck_timer = 0.0
                else:
                    self.stuck_timer = 0.0

    def _update_neutral(self, dt: float, units: List["Unit"],
                        projectiles: List["Projectile"],
                        events: Optional[List[dict]] = None) -> None:
        home = self.home_pos or self.pos
        target = None
        if (
            self.last_hit_by
            and self.last_hit_by.alive
            and dist(self.pos, home) <= self.leash_range
        ):
            target = self.last_hit_by
        if target is None:
            target = self._find_target(units)

        if target and dist(self.pos, home) <= self.leash_range:
            d = dist(self.pos, target.pos)
            if d <= self.atk_range:
                if self.atk_timer <= 0:
                    self._fire(projectiles, target, events)
            else:
                self._move_towards(target.pos, dt)
            return

        if dist(self.pos, home) > 0.2:
            self._move_towards(home, dt)

    def _update_hero(self, dt: float, units: List["Unit"], projectiles: List["Projectile"],
                     events: Optional[List[dict]] = None) -> None:
        if self.attack_target:
            tgt = self.attack_target
            if not tgt.alive:
                self.attack_target = None
            else:
                d = dist(self.pos, tgt.pos)
                if d <= self.atk_range:
                    self.move_target = None
                    if self.atk_timer <= 0:
                        self._fire(projectiles, tgt, events)
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
        if self.stun_timer > 0:
            return
        d = dist(self.pos, target)
        if d <= 0.0001:
            return
        step = min(self.speed * self.speed_mult * self.slow_mult * dt, d)
        self.pos = (
            self.pos[0] + (target[0] - self.pos[0]) / d * step,
            self.pos[1] + (target[1] - self.pos[1]) / d * step,
        )

    def _fire(self, projectiles: List["Projectile"], target: "Unit",
              events: Optional[List[dict]] = None) -> None:
        self.atk_timer = self.atk_cd

        # Ближний бой: удар мгновенный, без снаряда.
        if self.melee:
            target.take_damage(self.atk_dmg, attacker=self)
            if events is not None:
                angle = math.atan2(target.pos[1] - self.pos[1], target.pos[0] - self.pos[0])
                events.append({
                    "kind": "melee_attack",
                    "x": target.pos[0],
                    "y": target.pos[1],
                    "angle": angle,
                    "color": list(self.proj_color),
                    "team": self.team,
                })
            return

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
        acquire = self.atk_range + 1.5
        candidates = [
            u for u in units
            if u is not self and u.alive and u.team != self.team
            and dist(self.pos, u.pos) <= acquire
        ]
        if not candidates:
            return None

        def nearest(pool: List["Unit"]) -> "Unit":
            return min(pool, key=lambda u: dist(self.pos, u.pos))

        if self.kind == "tower":
            # Как в Dota: вышка сначала стреляет по крипам, и только если их нет —
            # по героям/другим юнитам.
            creeps = [u for u in candidates if u.kind in ("creep", "creep_ranged")]
            return nearest(creeps or candidates)

        if self.kind in ("creep", "creep_ranged"):
            # Крипы дерутся с крипами, затем с героями, затем с вышками.
            creeps = [u for u in candidates if u.kind in ("creep", "creep_ranged")]
            if creeps:
                return nearest(creeps)
            heroes = [u for u in candidates if u.kind == "hero"]
            if heroes:
                return nearest(heroes)
            return nearest(candidates)

        return nearest(candidates)

    # ----- коллизии -----
    def resolve_collision(self, other: "Unit") -> None:
        if self is other or not self.alive or not other.alive:
            return

        # Крипы не должны упираться в вышки/троны: иначе на линии они
        # навсегда застревают перед своей же вышкой.
        creeps = ("creep", "creep_ranged")
        fixed = ("tower", "throne")
        if (self.kind in creeps and other.kind in fixed) or (
            self.kind in fixed and other.kind in creeps
        ):
            return

        d = dist(self.pos, other.pos)
        min_dist = self.radius + other.radius

        if d < min_dist and d > 0.001:
            overlap = min_dist - d
            dx = (self.pos[0] - other.pos[0]) / d
            dy = (self.pos[1] - other.pos[1]) / d

            self_fixed = self.kind in ("tower", "throne")
            other_fixed = other.kind in ("tower", "throne")

            if not self_fixed and not other_fixed:
                self.pos = (self.pos[0] + dx * overlap * 0.5, self.pos[1] + dy * overlap * 0.5)
                other.pos = (other.pos[0] - dx * overlap * 0.5, other.pos[1] - dy * overlap * 0.5)
            elif not self_fixed:
                self.pos = (self.pos[0] + dx * overlap, self.pos[1] + dy * overlap)
            elif not other_fixed:
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
            if (
                self.kind == "hero"
                and attacker.owner_player
                and attacker.owner_player != self.owner_player
            ):
                self.damage_contributors.add(attacker.owner_player)

        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def apply_slow(self, mult: float, duration: float) -> None:
        self.slow_mult = min(self.slow_mult, max(0.1, mult))
        self.slow_timer = max(self.slow_timer, duration)


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
    hero_id: str = ""
    gold: float = 0.0
    cs: int = 0
    denies: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    level: int = 1
    xp: float = 0.0
    xp_next: float = 100.0
    respawn_timer: float = 0.0
    str: float = 0.0
    agi: float = 0.0
    int: float = 0.0
    mana: float = 0.0
    max_mana: float = 0.0
    items: List[str] = field(default_factory=list)
    cooldowns: Dict[int, float] = field(default_factory=dict)


# ---------- Мир ----------
class World:
    """Серверная/оффлайн-симуляция. Никакого рендера и ввода."""

    def __init__(self, data: dict):
        self.data = data
        self.cfg = data["settings"]
        self.map_cfg = data["map"]
        self.units_cfg = data["units"]
        self.heroes_data = data["heroes"]
        self.heroes = self.heroes_data["heroes"]
        self.progression = self.heroes_data.get("progression", {})
        self.items_data = data["items"]["items"]
        self.neutrals_data = data["neutrals"]
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
        self.neutral_respawns: List[dict] = []

        self.match_time = -30.0
        self.tick_count = 0
        self._next_uid = 1
        self.match_over = False
        self.winner = None

        self.creep_interval = self.cfg["timing"]["creep_interval"]
        self.creep_timer = self.creep_interval
        self.creeps_per_wave = self.cfg["timing"].get("creeps_per_wave", 5)
        self.ranged_creeps = int(self.cfg["timing"].get("ranged_creeps", 1))
        self.respawn_time = self.cfg["timing"].get("respawn_time", 5.0)
        self.xp_radius = float(self.cfg["timing"].get("xp_radius", 8.0))

        progression = self.progression
        self.max_level = int(progression.get("max_level", 10))
        self.xp_base = float(progression.get("xp_base", 100))
        self.xp_step = float(progression.get("xp_step", 50))
        self.respawn_per_level = float(progression.get("respawn_per_level", 1.0))
        self.hero_kill_gold_base = float(progression.get("hero_kill_gold_base", 150))
        self.hero_kill_gold_per_level = float(progression.get("hero_kill_gold_per_level", 25))
        self.hp_per_str = float(progression.get("hp_per_str", 12))
        self.mana_per_int = float(progression.get("mana_per_int", 8))
        self.armor_per_agi = float(progression.get("armor_per_agi", 0.15))
        self.damage_per_primary = float(progression.get("damage_per_primary", 0.8))
        self.attack_speed_per_agi = float(progression.get("attack_speed_per_agi", 0.006))
        self.starting_gold = float(progression.get("starting_gold", 600))
        self.mana_regen = float(progression.get("mana_regen", 3.0))
        self.shop_radius = float(self.cfg["timing"].get("shop_radius", 6.0))

        for t in self.map_cfg["towers"]:
            self._add_unit(self._make_tower(t["team"], t["pos"], self.units_cfg["tower"]))

        thrones = self.map_cfg.get("thrones")
        if thrones is None:
            thrones = [{"team": team, "pos": pos} for team, pos in self.bases.items()]
        for t in thrones:
            self._add_unit(self._make_throne(t["team"], t["pos"], self.units_cfg["throne"]))

        for camp in self.map_cfg.get("neutrals", []):
            self._spawn_neutral_camp(camp)

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
            xp_bounty=tpl.get("xp_bounty", 0),
            armor=tpl.get("armor", 0.0),
            proj_color=(255, 120, 50) if team == "B" else (255, 160, 80),
        )

    def _make_throne(self, team: str, pos, tpl: dict) -> Unit:
        return Unit(
            uid=0,
            team=team,
            kind="throne",
            pos=tuple(pos),
            hp=tpl["hp"],
            max_hp=tpl["hp"],
            speed=0.0,
            atk_range=0.0,
            atk_dmg=0.0,
            atk_cd=1.0,
            radius=tpl["radius"],
            projectile_speed=0.0,
            armor=tpl.get("armor", 0.0),
            proj_color=(255, 120, 50) if team == "B" else (255, 160, 80),
        )

    def _make_creep(self, team: str, lane_path, tpl: dict, rank: int = 0,
                    kind: str = "creep") -> Unit:
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
            kind=kind,
            pos=tuple(start),
            hp=tpl["hp"],
            max_hp=tpl["hp"],
            speed=tpl["speed"],
            atk_range=tpl["atk_range"],
            melee=bool(tpl.get("melee", kind == "creep")),
            atk_dmg=tpl["atk_dmg"],
            atk_cd=tpl["atk_cd"],
            radius=tpl["radius"],
            projectile_speed=tpl["projectile_speed"],
            gold_bounty=tpl.get("gold_bounty", 0),
            xp_bounty=tpl.get("xp_bounty", 0),
            waypoints=wps,
            wp_index=1,
            proj_color=(255, 240, 150),
        )

    def _spawn_neutral_camp(self, camp: dict) -> None:
        tpl_id = str(camp.get("type", ""))
        if tpl_id not in self.neutrals_data:
            return
        count = max(1, int(camp.get("count", 2)))
        center = tuple(camp.get("pos", (0, 0)))
        respawn = float(camp.get("respawn", 60))
        for index in range(count):
            angle = (2.0 * math.pi * index) / count
            offset = 0.55 if count > 1 else 0.0
            pos = (
                center[0] + math.cos(angle) * offset,
                center[1] + math.sin(angle) * offset,
            )
            self._spawn_neutral_unit(tpl_id, pos, str(camp.get("id", "")), respawn)

    def _spawn_neutral_unit(self, tpl_id: str, pos, camp_id: str,
                            respawn: float = 60.0) -> None:
        tpl = self.neutrals_data.get(tpl_id)
        if not tpl:
            return
        unit = Unit(
            uid=0,
            team="N",
            kind="neutral",
            pos=tuple(pos),
            hp=tpl["hp"],
            max_hp=tpl["hp"],
            speed=tpl["speed"],
            atk_range=tpl["atk_range"],
            melee=bool(tpl.get("melee", True)),
            atk_dmg=tpl["atk_dmg"],
            atk_cd=tpl["atk_cd"],
            radius=tpl["radius"],
            projectile_speed=tpl["projectile_speed"],
            gold_bounty=tpl.get("gold_bounty", 0),
            xp_bounty=tpl.get("xp_bounty", 0),
            armor=tpl.get("armor", 0.0),
            proj_color=(210, 180, 120),
            home_pos=tuple(pos),
            camp_id=camp_id,
            neutral_type=tpl_id,
            respawn_time=respawn,
        )
        self._add_unit(unit)

    def _queue_neutral_respawn(self, unit: Unit) -> None:
        if not unit.neutral_type:
            return
        self.neutral_respawns.append({
            "type": unit.neutral_type,
            "pos": unit.home_pos or unit.pos,
            "camp_id": unit.camp_id or "",
            "respawn": unit.respawn_time,
            "timer": unit.respawn_time,
        })

    def _update_neutral_respawns(self, dt: float) -> None:
        for item in list(self.neutral_respawns):
            item["timer"] -= dt
            if item["timer"] <= 0:
                self._spawn_neutral_unit(
                    item["type"], item["pos"], item["camp_id"], item["respawn"]
                )
                self.neutral_respawns.remove(item)

    def _spawn_pos(self, team: str, slot: int) -> Tuple[float, float]:
        base = self.spawns.get(team, self.bases.get(team, (2.0, 2.0)))
        return (base[0] + 0.8 * slot, base[1])

    # ----- игроки -----
    def _item_bonus(self, player: "PlayerState") -> Dict[str, float]:
        totals = {"hp": 0.0, "mana": 0.0, "damage": 0.0, "armor": 0.0, "speed": 0.0}
        for item_id in player.items:
            item = self.items_data.get(item_id)
            if not item:
                continue
            for key, value in item.get("bonus", {}).items():
                if key in totals:
                    totals[key] += float(value)
        return totals

    def _recompute_hero(self, player: "PlayerState", heal: bool = False) -> None:
        cfg = self.heroes[player.hero_id]
        base = cfg["base"]
        growth = cfg.get("growth", {})
        level = player.level

        player.str = base["str"] + growth.get("str", 0) * (level - 1)
        player.agi = base["agi"] + growth.get("agi", 0) * (level - 1)
        player.int = base["int"] + growth.get("int", 0) * (level - 1)

        bonus = self._item_bonus(player)
        hero = player.hero
        old_max_hp = hero.max_hp
        old_max_mana = player.max_mana

        primary_value = {
            "str": player.str,
            "agi": player.agi,
            "int": player.int,
        }.get(cfg.get("primary", "str"), player.str)

        hero.max_hp = base["hp"] + player.str * self.hp_per_str + bonus["hp"]
        hero.atk_dmg = base["damage"] + primary_value * self.damage_per_primary + bonus["damage"]
        hero.armor = base["armor"] + player.agi * self.armor_per_agi + bonus["armor"]
        hero.speed = base["speed"] + bonus["speed"]
        hero.atk_cd = base["atk_cd"] / (1.0 + player.agi * self.attack_speed_per_agi)
        hero.atk_range = base["atk_range"]
        hero.radius = base["radius"]
        hero.projectile_speed = base["projectile_speed"]

        player.max_mana = base["mana"] + player.int * self.mana_per_int + bonus["mana"]

        if heal:
            hero.hp = min(hero.max_hp, hero.hp + max(0.0, hero.max_hp - old_max_hp))
            player.mana = min(
                player.max_mana,
                player.mana + max(0.0, player.max_mana - old_max_mana),
            )
        else:
            hero.hp = min(hero.hp, hero.max_hp)
            player.mana = min(player.mana, player.max_mana)

    def add_player(self, player_id: str, team: str, name: str = "",
                   hero_id: Optional[str] = None) -> Unit:
        if player_id in self.players:
            return self.players[player_id].hero

        if hero_id not in self.heroes:
            hero_id = next(iter(self.heroes))

        cfg = self.heroes[hero_id]
        base = cfg["base"]
        slot = sum(1 for p in self.players.values() if p.team == team)
        spawn = self._spawn_pos(team, slot)

        hero = Unit(
            uid=0,
            team=team,
            kind="hero",
            pos=spawn,
            hp=base["hp"],
            max_hp=base["hp"],
            speed=base["speed"],
            atk_range=base["atk_range"],
            melee=bool(cfg.get("melee", False)),
            atk_dmg=base["damage"],
            atk_cd=base["atk_cd"],
            radius=base["radius"],
            projectile_speed=base["projectile_speed"],
            armor=base["armor"],
            proj_color=tuple(cfg.get("color", self.colors.get("hero", (240, 220, 120)))),
            owner_player=player_id,
        )
        self._add_unit(hero)

        player = PlayerState(
            player_id=player_id,
            team=team,
            hero=hero,
            name=name,
            slot=slot,
            hero_id=hero_id,
            gold=self.starting_gold,
            xp_next=self._xp_for_level(1),
        )
        self.players[player_id] = player
        self._recompute_hero(player, heal=True)
        hero.hp = hero.max_hp
        player.mana = player.max_mana
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

        elif ctype == "deny":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                return
            if (
                target
                and target.alive
                and target.team == hero.team
                and target.kind in ("creep", "creep_ranged")
                and target.hp <= 0.4 * target.max_hp
            ):
                hero.attack_target = target
                hero.move_target = None

        elif ctype == "buy":
            self._buy_item(player, str(cmd.get("item", "")))

        elif ctype == "cast":
            self._cast_ability(player, cmd)

    def _shop_error(self, player: "PlayerState", message: str) -> None:
        self.events.append({
            "kind": "shop_error",
            "player": player.player_id,
            "message": message,
        })

    def _buy_item(self, player: "PlayerState", item_id: str) -> None:
        item = self.items_data.get(item_id)
        if not item:
            return
        if item.get("unique") and item_id in player.items:
            self._shop_error(player, "Этот предмет уже куплен")
            return
        if len(player.items) >= 6:
            self._shop_error(player, "Инвентарь полон")
            return

        cost = int(item.get("cost", 0))
        if player.gold < cost:
            self._shop_error(player, "Недостаточно золота")
            return

        base = self.bases.get(player.team)
        if base and dist(player.hero.pos, base) > self.shop_radius:
            self._shop_error(player, "Нужно быть у своей базы")
            return

        player.gold -= cost
        player.items.append(item_id)
        self._recompute_hero(player, heal=True)
        self.events.append({
            "kind": "purchase",
            "player": player.player_id,
            "item": item_id,
            "gold": int(player.gold),
        })

    def _aoe_damage(self, caster: Unit, x: float, y: float, radius: float,
                    damage: float, slow: Optional[float] = None,
                    slow_duration: float = 0.0) -> None:
        for unit in self.units:
            if not unit.alive or unit.team == caster.team:
                continue
            if dist(unit.pos, (x, y)) <= radius:
                unit.take_damage(damage, attacker=caster)
                if slow:
                    unit.apply_slow(slow, slow_duration)

    def _cast_ability(self, player: "PlayerState", cmd: dict) -> None:
        hero = player.hero
        abilities = self.heroes[player.hero_id].get("abilities", [])
        try:
            slot = int(cmd.get("slot", -1))
        except (TypeError, ValueError):
            return
        if slot < 0 or slot >= len(abilities):
            return

        ability = abilities[slot]
        if player.cooldowns.get(slot, 0.0) > 0:
            return
        cost = float(ability.get("mana", 0))
        if player.mana < cost:
            return

        atype = ability.get("type")
        x, y = hero.pos
        used = False

        if atype == "target_damage":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                return
            if not target or not target.alive or target.team == hero.team:
                return
            if dist(hero.pos, target.pos) > float(ability.get("range", 5.0)) + 0.01:
                return
            target.take_damage(float(ability.get("damage", 0)), attacker=hero)
            if ability.get("slow"):
                target.apply_slow(
                    float(ability["slow"]),
                    float(ability.get("slow_duration", 2.0)),
                )
            x, y = target.pos
            used = True

        elif atype == "aoe_damage":
            try:
                x = float(cmd.get("x", hero.pos[0]))
                y = float(cmd.get("y", hero.pos[1]))
            except (TypeError, ValueError):
                return
            if dist(hero.pos, (x, y)) > float(ability.get("range", 5.0)) + 0.01:
                return
            self._aoe_damage(
                hero, x, y,
                float(ability.get("radius", 2.0)),
                float(ability.get("damage", 0)),
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
            )
            used = True

        elif atype == "aoe_self":
            x, y = hero.pos
            self._aoe_damage(
                hero, x, y,
                float(ability.get("radius", 2.0)),
                float(ability.get("damage", 0)),
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
            )
            used = True

        elif atype == "self_heal":
            hero.hp = min(hero.max_hp, hero.hp + float(ability.get("amount", 0)))
            x, y = hero.pos
            used = True

        elif atype == "speed_buff":
            hero.speed_mult = float(ability.get("multiplier", 1.5))
            hero.speed_buff_timer = float(ability.get("duration", 4.0))
            x, y = hero.pos
            used = True

        if not used:
            return

        player.mana -= cost
        player.cooldowns[slot] = float(ability.get("cooldown", 5.0))
        self.events.append({
            "kind": "ability",
            "player": player.player_id,
            "slot": slot,
            "ability_id": ability.get("id"),
            "name": ability.get("name"),
            "type": atype,
            "x": x,
            "y": y,
            "radius": float(ability.get("radius", 0.0)),
            "color": list(ability.get("color", [255, 255, 255])),
        })

    # ----- тик -----
    def tick(self, dt: float) -> None:
        if self.match_over:
            return

        dt = max(0.0, min(dt, 0.1))
        self.match_time += dt
        self.tick_count += 1

        # До 0:00 идёт отсчёт, крипы и пассивное золото ещё не работают.
        in_game = self.match_time >= 0.0

        for player in self.players.values():
            if in_game:
                player.gold += dt
            player.mana = min(player.max_mana, player.mana + self.mana_regen * dt)
            for slot in list(player.cooldowns):
                player.cooldowns[slot] = max(0.0, player.cooldowns[slot] - dt)

        # Волны крипов: первая на 0:00, дальше каждые 30 секунд.
        if in_game:
            self.creep_timer += dt
            while self.creep_timer >= self.creep_interval:
                self.creep_timer -= self.creep_interval
                self._spawn_creep_wave()

        # Юниты.
        for unit in list(self.units):
            if unit.alive:
                unit.update(dt, self.units, self.projectiles, self.events)

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

            if unit.kind == "throne":
                self._on_throne_death(unit)
            elif unit.kind == "hero":
                self._on_hero_death(unit)
            elif unit.kind == "neutral":
                self._on_unit_death(unit)
                self._queue_neutral_respawn(unit)
            elif unit.gold_bounty > 0 or unit.xp_bounty > 0:
                self._on_unit_death(unit)

        # Респавн героев и нейтралов.
        self._update_respawns(dt)
        self._update_neutral_respawns(dt)

        # Мёртвые герои остаются для респавна, мёртвые троны — как руины.
        self.units = [u for u in self.units if u.alive or u.kind in ("hero", "throne")]

    def _spawn_creep_wave(self) -> None:
        ranged_from = max(0, self.creeps_per_wave - self.ranged_creeps)
        for lane_name in self.lanes:
            path = self.lanes[lane_name]
            for team in ("A", "B"):
                for i in range(self.creeps_per_wave):
                    if i >= ranged_from:
                        tpl = self.units_cfg.get("creep_ranged", self.units_cfg["creep"])
                        kind = "creep_ranged"
                    else:
                        tpl = self.units_cfg["creep"]
                        kind = "creep"
                    self._add_unit(self._make_creep(team, path, tpl, rank=i, kind=kind))

    def _on_hero_death(self, unit: Unit) -> None:
        player = self.players.get(unit.owner_player)
        if not player:
            return

        player.deaths += 1
        # В Dota время респавна растёт с уровнем.
        player.respawn_timer = self.respawn_time + (player.level - 1) * self.respawn_per_level

        killer = unit.last_hit_by
        if killer and killer.owner_player in self.players:
            if killer.owner_player != unit.owner_player:
                killer_player = self.players[killer.owner_player]
                killer_player.kills += 1

                # Золото за убийство героя получает добивший.
                hero_gold = int(
                    self.hero_kill_gold_base
                    + player.level * self.hero_kill_gold_per_level
                )
                killer_player.gold += hero_gold
                self.events.append({
                    "kind": "bounty",
                    "player": killer_player.player_id,
                    "unit": unit.uid,
                    "amount": hero_gold,
                    "x": unit.pos[0],
                    "y": unit.pos[1],
                })

        # Помощники: все вражеские герои, которые успели нанести урон.
        killer_pid = killer.owner_player if killer else None
        for pid in list(unit.damage_contributors):
            if pid in self.players and pid != unit.owner_player and pid != killer_pid:
                self.players[pid].assists += 1
        unit.damage_contributors.clear()

        # Опыт за убийство героя получают все вражеские герои рядом.
        hero_xp = 100 + player.level * 20
        for other in self.players.values():
            if other.team == player.team or not other.hero.alive:
                continue
            if dist(other.hero.pos, unit.pos) <= self.xp_radius:
                self._add_xp(other, hero_xp)

        self.events.append({
            "kind": "hero_death",
            "player": unit.owner_player,
            "killer": killer.owner_player if killer else None,
            "x": unit.pos[0],
            "y": unit.pos[1],
            "respawn": player.respawn_timer,
        })

    def _on_throne_death(self, unit: Unit) -> None:
        if self.match_over:
            return
        self.match_over = True
        self.winner = "B" if unit.team == "A" else "A"
        self.events.append({
            "kind": "match_end",
            "winner": self.winner,
            "x": unit.pos[0],
            "y": unit.pos[1],
        })

    def _on_unit_death(self, unit: Unit) -> None:
        killer = unit.last_hit_by
        denied = False

        if killer and killer.owner_player in self.players:
            player = self.players[killer.owner_player]
            if player.team == unit.team:
                # Добивание своего крипа (deny).
                denied = True
                player.denies += 1
                self.events.append({
                    "kind": "deny",
                    "player": player.player_id,
                    "unit": unit.uid,
                    "x": unit.pos[0],
                    "y": unit.pos[1],
                })
            elif unit.gold_bounty > 0:
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
        self._award_xp(unit, 0.5 if denied else 1.0)

    def _award_xp(self, unit: Unit, multiplier: float = 1.0) -> None:
        """Опыт за смерть юнита получают все вражеские герои рядом."""
        xp = int(unit.xp_bounty * multiplier)
        if xp <= 0:
            return

        for player in self.players.values():
            if player.team == unit.team or not player.hero.alive:
                continue
            if dist(player.hero.pos, unit.pos) <= self.xp_radius:
                self._add_xp(player, xp)

        unit.xp_bounty = 0

    def _xp_for_level(self, level: int) -> float:
        return self.xp_base + (level - 1) * self.xp_step

    def _add_xp(self, player: PlayerState, amount: float) -> None:
        if amount <= 0 or player.level >= self.max_level:
            return

        player.xp += amount

        while player.level < self.max_level and player.xp >= player.xp_next:
            player.xp -= player.xp_next
            player.level += 1
            player.xp_next = self._xp_for_level(player.level)
            self._recompute_hero(player, heal=True)

            self.events.append({
                "kind": "level_up",
                "player": player.player_id,
                "level": player.level,
            })

        if player.level >= self.max_level:
            player.xp = min(player.xp, player.xp_next)

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
            hero.speed_mult = 1.0
            hero.speed_buff_timer = 0.0
            hero.slow_mult = 1.0
            hero.slow_timer = 0.0
            hero.stun_timer = 0.0
            hero.damage_contributors.clear()
            player.mana = player.max_mana

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
                "melee": u.melee,
                "neutral_type": u.neutral_type,
                "alive": u.alive,
            }
            if u.kind == "hero":
                entry.update({
                    "dmg": round(u.atk_dmg, 1),
                    "speed": u.speed,
                    "armor": u.armor,
                    "slow": u.slow_mult < 0.999,
                    "stunned": u.stun_timer > 0,
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
                "hero_id": p.hero_id,
                "gold": int(p.gold),
                "cs": p.cs,
                "denies": p.denies,
                "kills": p.kills,
                "deaths": p.deaths,
                "assists": p.assists,
                "level": p.level,
                "xp": round(p.xp, 1),
                "xp_next": round(p.xp_next, 1),
                "str": round(p.str, 1),
                "agi": round(p.agi, 1),
                "int": round(p.int, 1),
                "mana": round(p.mana, 1),
                "max_mana": round(p.max_mana, 1),
                "items": list(p.items),
                "cooldowns": {
                    str(slot): round(cd, 2) for slot, cd in p.cooldowns.items()
                },
                "respawn": round(p.respawn_timer, 2),
                "hero": p.hero.uid if p.hero else None,
            }
            for pid, p in self.players.items()
        }

        return {
            "tick": self.tick_count,
            "time": round(self.match_time, 3),
            "over": self.match_over,
            "winner": self.winner,
            "units": units,
            "projectiles": projectiles,
            "players": players,
        }
