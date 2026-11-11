"""Авторитетная симуляция мира.

Модуль намеренно не импортирует pygame: его использует и headless-сервер,
и оффлайн-клиент. Всё, что связано с картинкой, вводом и камерой, живёт
в game.py / ui.py.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import math
import random

from shared import formulas


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
    armor_debuff: float = 0.0
    armor_debuff_timer: float = 0.0
    facing: Tuple[float, float] = (1.0, 0.0)
    cast_lock_timer: float = 0.0
    magic_resist: float = 0.0
    magic_immune_timer: float = 0.0
    silence_timer: float = 0.0
    root_timer: float = 0.0
    fear_timer: float = 0.0
    item_mute_timer: float = 0.0
    invisible_timer: float = 0.0
    true_sight_timer: float = 0.0
    evasion: float = 0.0
    damage_reduction: float = 0.0
    reflect: float = 0.0
    crit_chance: float = 0.0
    crit_mult: float = 1.75
    lifesteal: float = 0.0
    spell_amp: float = 0.0
    attack_point: float = 0.0
    backswing: float = 0.0
    backswing_timer: float = 0.0
    windup_timer: float = 0.0
    windup_target: Optional["Unit"] = None
    is_boss: bool = False
    boss_phase: int = 1
    boss_phase_changed: bool = False
    courier_hits: int = 0
    courier_respawn: float = 0.0
    carrying: List[str] = field(default_factory=list)
    camp_touched_at: float = 0.0
    camp_stacks: int = 1
    innate_type: str = ""
    innate_value: float = 0.0
    first_hit_block_timer: float = 0.0
    spell_burn: float = 0.0
    orbs: List[dict] = field(default_factory=list)
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

        # Снижение брони (например, от «Дальнего разреза»).
        self.armor_debuff_timer = max(0.0, self.armor_debuff_timer - dt)
        if self.armor_debuff_timer <= 0:
            self.armor_debuff = 0.0

        self.cast_lock_timer = max(0.0, self.cast_lock_timer - dt)
        for attr in (
            "magic_immune_timer", "silence_timer", "root_timer", "fear_timer",
            "item_mute_timer", "invisible_timer", "true_sight_timer",
            "first_hit_block_timer", "backswing_timer",
        ):
            value = max(0.0, getattr(self, attr) - dt)
            setattr(self, attr, value)

        self.stun_timer = max(0.0, self.stun_timer - dt)
        if self.stun_timer > 0:
            return
        if self.fear_timer > 0:
            return

        if self.kind == "hero":
            self._update_hero(dt, units, projectiles, events)
            return

        if self.kind == "neutral":
            self._update_neutral(dt, units, projectiles, events)
            return

        if self.kind == "courier":
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

    def _attack_step(self, dt: float, target: "Unit",
                     projectiles: List["Projectile"],
                     events: Optional[List[dict]] = None) -> bool:
        """Возвращает True, если атака уже началась/идёт (стоять на месте)."""
        if target is None or not target.alive:
            self.windup_timer = 0.0
            self.windup_target = None
            return False
        d = dist(self.pos, target.pos)
        if self.windup_target is target and self.windup_timer > 0:
            if d > self.atk_range + 0.25:
                self.windup_timer = 0.0
                self.windup_target = None
                return False
            self.windup_timer = max(0.0, self.windup_timer - dt)
            if self.windup_timer <= 0:
                self._fire(projectiles, target, events)
                self.windup_target = None
            return True
        if d <= self.atk_range:
            self.move_target = None
            if self.atk_timer <= 0:
                if self.attack_point > 0.01:
                    self.windup_target = target
                    self.windup_timer = self.attack_point
                else:
                    self._fire(projectiles, target, events)
            return True
        return False

    def _update_hero(self, dt: float, units: List["Unit"], projectiles: List["Projectile"],
                     events: Optional[List[dict]] = None) -> None:
        # Во время подготовки ультимейта герой не двигается и не атакует.
        if self.cast_lock_timer > 0:
            return

        if self.root_timer > 0:
            self.move_target = None
            if self.attack_target and self.attack_target.alive:
                self._attack_step(dt, self.attack_target, projectiles, events)
            return

        if self.attack_target:
            tgt = self.attack_target
            if not tgt.alive:
                self.attack_target = None
                self.windup_timer = 0.0
                self.windup_target = None
            else:
                if self._attack_step(dt, tgt, projectiles, events):
                    return
                self._move_towards(tgt.pos, dt)
            return

        if self.move_target:
            d = dist(self.pos, self.move_target)
            if d < 0.1:
                self.move_target = None
            else:
                self._move_towards(self.move_target, dt)

    def _move_towards(self, target: Tuple[float, float], dt: float) -> None:
        if self.stun_timer > 0 or self.root_timer > 0 or self.fear_timer > 0:
            return
        d = dist(self.pos, target)
        if d <= 0.0001:
            return
        ndx = (target[0] - self.pos[0]) / d
        ndy = (target[1] - self.pos[1]) / d
        self.facing = (ndx, ndy)
        step = min(self.speed * self.speed_mult * self.slow_mult * dt, d)
        self.pos = (
            self.pos[0] + ndx * step,
            self.pos[1] + ndy * step,
        )

    def _fire(self, projectiles: List["Projectile"], target: "Unit",
              events: Optional[List[dict]] = None) -> None:
        self.atk_timer = self.atk_cd
        if self.innate_type == "low_hp_as" and self.hp <= self.max_hp * 0.35:
            self.atk_timer = self.atk_cd / (1.0 + self.innate_value)

        d = dist(self.pos, target.pos)
        if d > 0.0001:
            self.facing = (
                (target.pos[0] - self.pos[0]) / d,
                (target.pos[1] - self.pos[1]) / d,
            )

        damage = self.atk_dmg
        if self.crit_chance > 0 and formulas.roll_crit(self.crit_chance):
            damage = formulas.crit_damage(damage, self.crit_mult)
        if self.innate_type == "backstab":
            to_attacker = (self.pos[0] - target.pos[0], self.pos[1] - target.pos[1])
            dot = to_attacker[0] * target.facing[0] + to_attacker[1] * target.facing[1]
            if dot < 0:
                damage *= 1.0 + self.innate_value

        orb = self.orbs[0] if self.orbs else {}
        if self.melee:
            self.backswing_timer = self.backswing
            target.take_damage(damage, attacker=self, damage_type="physical")
            if orb:
                apply_orb_effect(self, target, orb, None)
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
            dmg=damage,
            team=self.team,
            owner=self,
            speed=self.projectile_speed,
            color=self.proj_color,
            radius=8 if self.kind == "tower" else 4,
            orb=orb,
            damage_type="physical",
        ))

    def _find_target(self, units: List["Unit"]) -> Optional["Unit"]:
        acquire = self.atk_range + 1.5
        candidates = [
            u for u in units
            if u is not self and u.alive and u.team != self.team
            and (u.invisible_timer <= 0 or self.true_sight_timer > 0)
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
    def take_damage(self, dmg: float, attacker: Optional["Unit"] = None,
                    damage_type: str = "physical") -> None:
        if not self.alive:
            return

        if self.kind == "courier":
            if dmg > 0:
                self.courier_hits = max(0, self.courier_hits - 1)
                self.hp = self.max_hp * (self.courier_hits / 3.0)
                if self.courier_hits <= 0:
                    self.hp = 0.0
                    self.alive = False
                    self.courier_respawn = formulas.COURIER_RESPAWN
            return

        if self.invisible_timer > 0 and attacker is not None:
            self.invisible_timer = 0.0

        # Уклонение работает только против физических атак.
        if damage_type == "physical" and self.evasion > 0 and attacker is not None:
            if formulas.roll_evasion(self.evasion):
                return

        # Врождённая защита: первый удар раз в 8 секунд режется.
        if (
            self.innate_type == "first_hit_block"
            and self.first_hit_block_timer <= 0
            and attacker is not None
        ):
            self.first_hit_block_timer = 8.0
            dmg = float(dmg) * (1.0 - max(0.0, min(0.9, self.innate_value)))

        effective_armor = max(-15.0, self.armor - self.armor_debuff)
        effective = formulas.damage_after_resists(
            dmg,
            damage_type=damage_type,
            armor=effective_armor,
            magic_resist=self.magic_resist,
            magic_immune=self.magic_immune_timer > 0,
            damage_reduction=self.damage_reduction,
        )
        self.hp -= effective

        if attacker:
            self.last_hit_by = attacker
            if (
                self.kind == "hero"
                and attacker.owner_player
                and attacker.owner_player != self.owner_player
            ):
                self.damage_contributors.add(attacker.owner_player)
            if damage_type == "physical" and attacker.lifesteal > 0 and effective > 0:
                attacker.hp = min(attacker.max_hp, attacker.hp + effective * attacker.lifesteal)

        if self.reflect > 0 and attacker is not None and effective > 0:
            attacker.take_damage(
                effective * self.reflect, attacker=None, damage_type="pure"
            )

        if self.hp <= 0:
            self.hp = 0
            self.alive = False

    def apply_slow(self, mult: float, duration: float) -> None:
        self.slow_mult = min(self.slow_mult, max(0.1, mult))
        self.slow_timer = max(self.slow_timer, duration)

    def apply_armor_break(self, amount: float, duration: float) -> None:
        if amount <= 0:
            return
        self.armor_debuff = max(self.armor_debuff, float(amount))
        self.armor_debuff_timer = max(self.armor_debuff_timer, float(duration))

    def apply_stun(self, duration: float) -> None:
        self.stun_timer = max(self.stun_timer, float(duration))

    def apply_silence(self, duration: float) -> None:
        self.silence_timer = max(self.silence_timer, float(duration))

    def apply_root(self, duration: float) -> None:
        self.root_timer = max(self.root_timer, float(duration))

    def apply_fear(self, duration: float) -> None:
        self.fear_timer = max(self.fear_timer, float(duration))

    def apply_item_mute(self, duration: float) -> None:
        self.item_mute_timer = max(self.item_mute_timer, float(duration))

    def apply_invisibility(self, duration: float) -> None:
        self.invisible_timer = max(self.invisible_timer, float(duration))

    def apply_true_sight(self, duration: float) -> None:
        self.true_sight_timer = max(self.true_sight_timer, float(duration))


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
    orb: dict = field(default_factory=dict)
    damage_type: str = "physical"

    def update(self, dt: float, units: Optional[List[Unit]] = None) -> None:
        if not self.alive or not self.target.alive:
            self.alive = False
            return

        d = dist(self.pos, self.target.pos)
        if d < 0.15:
            self.target.take_damage(self.dmg, attacker=self.owner,
                                    damage_type=self.damage_type)
            if self.orb:
                apply_orb_effect(self.owner, self.target, self.orb, units)
            self.alive = False
            return

        step = self.speed * dt
        self.pos = (
            self.pos[0] + (self.target.pos[0] - self.pos[0]) / d * min(step, d),
            self.pos[1] + (self.target.pos[1] - self.pos[1]) / d * min(step, d),
        )


@dataclass
class SoulProjectile:
    """Душа из ультимейта S: летит по прямой и бьёт каждого врага один раз."""

    pos: Tuple[float, float]
    vel: Tuple[float, float]
    dmg: float
    team: str
    owner: Unit
    speed: float = 9.0
    radius: float = 0.25
    max_dist: float = 10.0
    traveled: float = 0.0
    alive: bool = True
    color: Tuple[int, int, int] = (205, 125, 255)
    uid: int = 0
    hit_ids: set = field(default_factory=set)
    slow: Optional[float] = None
    slow_duration: float = 0.0
    damage_type: str = "magical"

    def update(self, dt: float, units: List[Unit]) -> None:
        if not self.alive:
            return

        step = self.speed * dt
        self.pos = (
            self.pos[0] + self.vel[0] * step,
            self.pos[1] + self.vel[1] * step,
        )
        self.traveled += step

        for unit in units:
            if not unit.alive or unit.team == self.team:
                continue
            if unit.uid in self.hit_ids:
                continue
            if dist(self.pos, unit.pos) <= self.radius + unit.radius:
                unit.take_damage(self.dmg, attacker=self.owner,
                                 damage_type=self.damage_type)
                if self.slow:
                    unit.apply_slow(self.slow, self.slow_duration)
                self.hit_ids.add(unit.uid)

        if self.traveled >= self.max_dist:
            self.alive = False


def apply_orb_effect(owner: Unit, target: Unit, orb: dict,
                     units: Optional[List[Unit]] = None) -> None:
    """Уникальные модификаторы атаки (орб-эффекты)."""
    if not orb:
        return
    kind = orb.get("type")
    if kind == "slow":
        target.apply_slow(float(orb.get("value", 0.35)),
                          float(orb.get("duration", 2.0)))
    elif kind == "armor_break":
        target.apply_armor_break(float(orb.get("value", 5)),
                                 float(orb.get("duration", 4.0)))
    elif kind == "chain":
        if random.random() > float(orb.get("chance", 0.25)):
            return
        jumps = int(orb.get("jumps", 3))
        dmg = float(orb.get("damage", 50))
        hit = {target.uid}
        current = target
        pool = units or []
        for _ in range(jumps):
            candidates = [
                u for u in pool
                if u.alive and u.team != owner.team and u.uid not in hit
                and dist(u.pos, current.pos) <= 3.0
            ]
            if not candidates:
                break
            current = min(candidates, key=lambda u: dist(u.pos, current.pos))
            hit.add(current.uid)
            current.take_damage(dmg, attacker=owner, damage_type="magical")


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
    reliable_gold: float = 0.0
    unreliable_gold: float = 0.0
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
    soul_stacks: int = 0
    item_cooldowns: Dict[str, float] = field(default_factory=dict)
    neutral_items: List[str] = field(default_factory=list)
    talent_choices: Dict[int, int] = field(default_factory=dict)
    pending_talents: List[int] = field(default_factory=list)
    talent_offers: Dict[int, list] = field(default_factory=dict)
    agha_abilities: set = field(default_factory=set)
    shard_abilities: set = field(default_factory=set)
    has_agha: bool = False
    has_shard: bool = False


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
        self.heroes_meta = data.get("heroes_meta", {})
        self.progression = self.heroes_data.get("progression", {})
        self.items_data = data["items"]["items"]
        self.neutral_items_data = data["items"].get("neutral_items", {})
        self.neutrals_data = data["neutrals"]
        self.colors = {k: tuple(v) for k, v in self.cfg["colors"].items()}
        self.rng = random.Random()

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
        self.souls: List[SoulProjectile] = []
        self.pending_bursts: List[dict] = []
        self.players: Dict[str, PlayerState] = {}
        self.events: List[dict] = []
        self.neutral_respawns: List[dict] = []
        self.runes: List[dict] = []
        self.boss: Optional[Unit] = None
        self.boss_respawn_timer = 0.0
        self.team_buffs: Dict[str, float] = {"A": 0.0, "B": 0.0}
        self.team_agha = {"A": 0, "B": 0}
        self.team_shard = {"A": 0, "B": 0}
        self._neutral_hp: Dict[int, float] = {}
        self.camp_stacks: Dict[str, int] = {}
        self.camp_touched_at: Dict[str, float] = {}
        self.camps = {
            str(c.get("id", "")): c
            for c in self.map_cfg.get("neutrals", [])
        }
        self.training = False

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
        self.max_level = max(25, int(progression.get("max_level", 10)))
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

        self._init_runes()
        self._spawn_boss()

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
            gold_bounty=tpl.get("gold_bounty", 0) or 250,
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
            gold_bounty=formulas.roll_gold(kind, self.rng),
            xp_bounty=formulas.roll_xp(kind, self.rng),
            waypoints=wps,
            wp_index=1,
            proj_color=(255, 240, 150),
        )

    def _spawn_neutral_camp(self, camp: dict) -> None:
        tpl_id = str(camp.get("type", ""))
        if tpl_id not in self.neutrals_data:
            return
        camp_id = str(camp.get("id", ""))
        count = max(1, int(camp.get("count", 2)))
        stacks = max(1, int(self.camp_stacks.get(camp_id, 1)))
        total = count * stacks
        center = tuple(camp.get("pos", (0, 0)))
        respawn = float(camp.get("respawn", 60))
        for index in range(total):
            angle = (2.0 * math.pi * index) / max(1, total)
            offset = 0.55 if total > 1 else 0.0
            pos = (
                center[0] + math.cos(angle) * offset,
                center[1] + math.sin(angle) * offset,
            )
            self._spawn_neutral_unit(tpl_id, pos, camp_id, respawn)
        self.camp_stacks.setdefault(camp_id, stacks)
        self.camp_touched_at.setdefault(camp_id, self.match_time)

    def _spawn_neutral_unit(self, tpl_id: str, pos, camp_id: str,
                            respawn: float = 60.0) -> Optional[Unit]:
        tpl = self.neutrals_data.get(tpl_id)
        if not tpl:
            return None
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
            gold_bounty=tpl.get("gold_bounty", 0) if tpl_id == "river_boss"
            else formulas.roll_gold("neutral", self.rng),
            xp_bounty=tpl.get("xp_bounty", 0) if tpl_id == "river_boss"
            else formulas.roll_xp("neutral", self.rng),
            armor=tpl.get("armor", 0.0),
            magic_resist=tpl.get("magic_resist", 0.0),
            proj_color=(210, 180, 120),
            home_pos=tuple(pos),
            camp_id=camp_id,
            neutral_type=tpl_id,
            respawn_time=respawn,
        )
        self._add_unit(unit)
        self._neutral_hp[unit.uid] = unit.hp
        return unit

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

    def _track_neutral_damage(self) -> None:
        for unit in self.units:
            if unit.kind != "neutral" or unit.is_boss:
                continue
            old = self._neutral_hp.get(unit.uid)
            if old is not None and unit.hp < old - 1e-6:
                camp_id = unit.camp_id or ""
                if camp_id:
                    self.camp_touched_at[camp_id] = self.match_time
            self._neutral_hp[unit.uid] = unit.hp

    def _update_camp_stacks(self) -> None:
        for camp_id, camp in self.camps.items():
            if not camp_id:
                continue
            stacks = int(self.camp_stacks.get(camp_id, 1))
            if stacks >= formulas.NEUTRAL_STACK_MAX:
                continue
            touched = self.camp_touched_at.get(camp_id, self.match_time)
            if self.match_time - touched < formulas.NEUTRAL_STACK_INTERVAL:
                continue
            alive = [
                u for u in self.units
                if u.alive and u.kind == "neutral" and u.camp_id == camp_id
            ]
            if not alive:
                continue
            self.camp_stacks[camp_id] = stacks + 1
            self.camp_touched_at[camp_id] = self.match_time
            tpl_id = str(camp.get("type", ""))
            count = max(1, int(camp.get("count", 2)))
            center = tuple(camp.get("pos", (0, 0)))
            respawn = float(camp.get("respawn", 60))
            for index in range(count):
                angle = (2.0 * math.pi * index) / max(1, count)
                pos = (
                    center[0] + math.cos(angle) * 0.75,
                    center[1] + math.sin(angle) * 0.75,
                )
                self._spawn_neutral_unit(tpl_id, pos, camp_id, respawn)
            self.events.append({
                "kind": "camp_stack",
                "camp": camp_id,
                "stacks": stacks + 1,
                "x": center[0],
                "y": center[1],
            })

    def _init_runes(self) -> None:
        points = [tuple(p) for p in self.map_cfg.get("runes", [])]
        self.rng.shuffle(points)
        kinds = ["wealth", "wealth", "wisdom", "wisdom"]
        self.runes = []
        for index, pos in enumerate(points[:4]):
            self.runes.append({
                "kind": kinds[index % len(kinds)],
                "pos": pos,
                "timer": 0.0,
                "active": True,
            })

    def _active_rune_positions(self) -> List[Tuple[float, float]]:
        return [r["pos"] for r in self.runes if r["active"]]

    def _respawn_rune(self, rune: dict) -> None:
        points = [tuple(p) for p in self.map_cfg.get("runes", [])]
        free = [p for p in points if p not in self._active_rune_positions()]
        rune["pos"] = self.rng.choice(free or points or [rune["pos"]])
        rune["kind"] = self.rng.choice(["wealth", "wisdom"])
        rune["timer"] = 0.0
        rune["active"] = True

    def _update_runes(self, dt: float) -> None:
        for rune in self.runes:
            if not rune["active"]:
                rune["timer"] = max(0.0, rune["timer"] - dt)
                if rune["timer"] <= 0:
                    self._respawn_rune(rune)
                continue
            for player in self.players.values():
                hero = player.hero
                if not hero.alive:
                    continue
                if dist(hero.pos, rune["pos"]) <= 0.9:
                    if rune["kind"] == "wealth":
                        amount = self.rng.randint(80, 120)
                        player.unreliable_gold += amount
                        player.gold += amount
                    else:
                        amount = self.rng.randint(60, 100)
                        self._add_xp(player, amount)
                    rune["active"] = False
                    rune["timer"] = formulas.RUNE_RESPAWN
                    self.events.append({
                        "kind": "rune",
                        "player": player.player_id,
                        "rune": rune["kind"],
                        "x": rune["pos"][0],
                        "y": rune["pos"][1],
                    })
                    break

    def _spawn_boss(self) -> None:
        boss_cfg = self.map_cfg.get("boss") or {}
        pos = tuple(boss_cfg.get("pos", (self.grid_w / 2, self.grid_h / 2)))
        unit = self._spawn_neutral_unit("river_boss", pos, "boss", 9999.0)
        if unit is not None:
            unit.is_boss = True
            unit.boss_phase = 1
            unit.gold_bounty = 400
            unit.xp_bounty = 500
            self.boss = unit
        self.boss_respawn_timer = 0.0

    def _update_boss(self, dt: float) -> None:
        if self.boss is None or not self.boss.alive:
            if self.boss_respawn_timer > 0:
                self.boss_respawn_timer = max(0.0, self.boss_respawn_timer - dt)
                if self.boss_respawn_timer <= 0:
                    self._spawn_boss()
            return

        boss = self.boss
        if boss.boss_phase == 1 and boss.hp <= boss.max_hp * 0.5:
            boss.boss_phase = 2
            boss.atk_dmg *= 1.3
            boss.speed *= 1.15
            boss.armor += 4
            boss.boss_phase_changed = True
            self.events.append({
                "kind": "boss_phase",
                "phase": 2,
                "x": boss.pos[0],
                "y": boss.pos[1],
            })

    def _on_boss_death(self, unit: Unit) -> None:
        killer = unit.last_hit_by
        team = None
        if killer and killer.owner_player in self.players:
            team = self.players[killer.owner_player].team
        if team:
            self.team_buffs[team] = 180.0
            for player in self.players.values():
                if player.team == team:
                    self._recompute_hero(player)
            self.events.append({
                "kind": "boss_drop",
                "team": team,
                "player": killer.owner_player if killer else None,
                "x": unit.pos[0],
                "y": unit.pos[1],
            })
        self.boss = None
        boss_cfg = self.map_cfg.get("boss") or {}
        low, high = boss_cfg.get("respawn", [480.0, 660.0])
        self.boss_respawn_timer = self.rng.uniform(float(low), float(high))
        self.events.append({
            "kind": "boss_death",
            "x": unit.pos[0],
            "y": unit.pos[1],
            "respawn": self.boss_respawn_timer,
        })

    def _spawn_pos(self, team: str, slot: int) -> Tuple[float, float]:
        base = self.spawns.get(team, self.bases.get(team, (2.0, 2.0)))
        return (base[0] + 0.8 * slot, base[1])

    def _spawn_courier(self, player: "PlayerState") -> Unit:
        base = self.bases.get(player.team, self._spawn_pos(player.team, player.slot))
        pos = (base[0] + 0.6, base[1] + 0.6)
        courier = Unit(
            uid=0,
            team=player.team,
            kind="courier",
            pos=pos,
            hp=3,
            max_hp=3,
            speed=1.8,
            atk_range=0.0,
            atk_dmg=0.0,
            radius=0.12,
            armor=0,
            owner_player=player.player_id,
            courier_hits=3,
            proj_color=(230, 210, 140),
        )
        courier.facing = (1.0, 0.0)
        return self._add_unit(courier)

    def _update_couriers(self, dt: float) -> None:
        for player in self.players.values():
            courier = next(
                (u for u in self.units if u.kind == "courier"
                 and u.owner_player == player.player_id),
                None,
            )
            if courier is None:
                if player.hero.alive:
                    self._spawn_courier(player)
                continue
            if not courier.alive:
                courier.courier_respawn = max(0.0, courier.courier_respawn - dt)
                if courier.courier_respawn <= 0:
                    base = self.bases.get(player.team, self._spawn_pos(player.team, player.slot))
                    courier.alive = True
                    courier.courier_hits = 3
                    courier.hp = 3
                    courier.max_hp = 3
                    courier.pos = (base[0] + 0.6, base[1] + 0.6)
                continue
            hero = player.hero
            if not hero.alive:
                continue
            d = dist(courier.pos, hero.pos)
            if d > 1.2:
                courier._move_towards(hero.pos, dt)
            elif courier.carrying:
                while courier.carrying and len(player.items) < 6:
                    item_id = courier.carrying.pop(0)
                    player.items.append(item_id)
                if not courier.carrying:
                    self._recompute_hero(player, heal=True)
                    self.events.append({
                        "kind": "courier_delivered",
                        "player": player.player_id,
                        "x": hero.pos[0],
                        "y": hero.pos[1],
                    })

    # ----- игроки -----
    def _item_bonus(self, player: "PlayerState") -> Dict[str, float]:
        totals = {
            "hp": 0.0, "mana": 0.0, "damage": 0.0, "armor": 0.0, "speed": 0.0,
            "str": 0.0, "agi": 0.0, "int": 0.0, "magic_resist": 0.0,
            "evasion": 0.0, "attack_speed": 0.0, "damage_reduction": 0.0,
            "reflect": 0.0, "crit": 0.0, "lifesteal": 0.0, "attack_range": 0.0,
            "spell_amp": 0.0,
        }
        for item_id in list(player.items) + list(player.neutral_items):
            item = self.items_data.get(item_id) or self.neutral_items_data.get(item_id)
            if not item:
                continue
            for key, value in item.get("bonus", {}).items():
                if key in totals:
                    totals[key] += float(value)
        return totals

    def _hero_meta(self, player: "PlayerState") -> dict:
        return self.heroes_meta.get(player.hero_id, {})

    def _talent_totals(self, player: "PlayerState") -> Dict[str, float]:
        totals = {
            "str": 0.0, "agi": 0.0, "int": 0.0, "hp": 0.0, "mana": 0.0,
            "armor": 0.0, "magic_resist": 0.0, "evasion": 0.0,
            "attack_speed": 0.0, "crit": 0.0, "spell_amp": 0.0,
        }
        meta = self._hero_meta(player)
        talents = meta.get("talents", {})
        for level, choice_index in player.talent_choices.items():
            offers = talents.get(str(level), [])
            if not (0 <= choice_index < len(offers)):
                continue
            effect = offers[choice_index].get("effect", {})
            kind = effect.get("type")
            value = float(effect.get("value", 0.0))
            if kind == "stat":
                key = effect.get("stat", "str")
                if key in totals:
                    totals[key] += value
            elif kind in totals:
                totals[kind] += value
        return totals

    def _recompute_hero(self, player: "PlayerState", heal: bool = False) -> None:
        cfg = self.heroes[player.hero_id]
        base = cfg["base"]
        meta = self._hero_meta(player)
        level = player.level

        attrs = formulas.attribute_growth(base, cfg.get("primary", "str"), level)
        bonus = self._item_bonus(player)
        talents = self._talent_totals(player)
        innate = meta.get("innate", {})

        player.str = attrs["str"] + bonus["str"] + talents["str"]
        player.agi = attrs["agi"] + bonus["agi"] + talents["agi"]
        player.int = attrs["int"] + bonus["int"] + talents["int"]

        hero = player.hero
        old_max_hp = hero.max_hp
        old_max_mana = player.max_mana

        primary_value = {
            "str": player.str,
            "agi": player.agi,
            "int": player.int,
        }.get(cfg.get("primary", "str"), player.str)

        passive = cfg.get("passive") or {}
        soul_bonus = 0.0
        if passive.get("type") == "soul_harvest":
            soul_bonus = player.soul_stacks * float(passive.get("damage_per_soul", 0.0))

        coeff = float(meta.get("coefficient", self.damage_per_primary))
        boss_damage = 1.15 if self.team_buffs.get(player.team, 0.0) > 0 else 1.0
        boss_armor = 3.0 if self.team_buffs.get(player.team, 0.0) > 0 else 0.0

        hero.max_hp = (
            base["hp"] + player.str * self.hp_per_str
            + bonus["hp"] + talents["hp"]
        )
        hero.atk_dmg = (
            formulas.hero_damage(base["damage"], primary_value, coeff)
            + bonus["damage"] + soul_bonus
        ) * boss_damage
        hero.armor = (
            base["armor"] + formulas.armor_from_agi(player.agi)
            + bonus["armor"] + talents["armor"] + boss_armor
        )
        hero.speed = base["speed"] + bonus["speed"]

        base_as = 1.0 / max(0.1, float(base["atk_cd"]))
        as_mult = 1.0 + bonus["attack_speed"] + talents["attack_speed"]
        hero.atk_cd = 1.0 / formulas.attacks_per_second(base_as * as_mult, player.agi)
        hero.atk_range = base["atk_range"] + bonus["attack_range"] + talents.get("attack_range", 0.0)
        hero.radius = base["radius"]
        hero.projectile_speed = base["projectile_speed"]
        hero.attack_point = float(meta.get("attack_point", 0.35))
        hero.backswing = float(meta.get("backswing", 0.25))

        hero.magic_resist = min(
            0.75,
            0.25 + bonus["magic_resist"] + talents["magic_resist"]
            + (float(innate.get("value", 0.0)) if innate.get("type") == "magic_resist" else 0.0),
        )
        hero.evasion = min(
            0.75,
            bonus["evasion"] + talents["evasion"]
            + (float(innate.get("value", 0.0)) if innate.get("type") == "evasion" else 0.0),
        )
        hero.damage_reduction = min(0.80, bonus["damage_reduction"])
        hero.reflect = min(1.0, bonus["reflect"])
        hero.crit_chance = min(1.0, bonus["crit"] + talents["crit"])
        hero.lifesteal = min(1.0, bonus["lifesteal"])
        hero.spell_amp = bonus["spell_amp"] + talents["spell_amp"]
        hero.orbs = [
            item["orb"]
            for item_id in list(player.items) + list(player.neutral_items)
            if (item := (self.items_data.get(item_id) or self.neutral_items_data.get(item_id)))
            and item.get("orb")
        ]
        hero.innate_type = str(innate.get("type", ""))
        hero.innate_value = float(innate.get("value", 0.0))
        if innate.get("type") == "attack_range":
            hero.atk_range += float(innate.get("value", 0.0))
        if innate.get("type") == "aura_armor":
            hero.armor += float(innate.get("value", 0.0))
        if innate.get("type") == "spell_burn":
            hero.spell_burn = float(innate.get("value", 0.0))

        player.max_mana = (
            base["mana"] + player.int * self.mana_per_int
            + bonus["mana"] + talents["mana"]
        )

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
            magic_resist=0.25,
            proj_color=tuple(cfg.get("color", self.colors.get("hero", (240, 220, 120)))),
            owner_player=player_id,
        )
        enemy_base = self.bases.get("B" if team == "A" else "A")
        if enemy_base:
            dx = enemy_base[0] - spawn[0]
            dy = enemy_base[1] - spawn[1]
            length = math.hypot(dx, dy)
            if length > 0.001:
                hero.facing = (dx / length, dy / length)
        self._add_unit(hero)

        player = PlayerState(
            player_id=player_id,
            team=team,
            hero=hero,
            name=name,
            slot=slot,
            hero_id=hero_id,
            gold=self.starting_gold,
            reliable_gold=0.0,
            unreliable_gold=self.starting_gold,
            xp_next=self._xp_for_level(1),
        )
        self.players[player_id] = player
        self._recompute_hero(player, heal=True)
        hero.hp = hero.max_hp
        player.mana = player.max_mana
        self._spawn_courier(player)
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
            hero.windup_timer = 0.0
            hero.windup_target = None

        elif ctype == "attack":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                return
            if target and target.alive and target.team != hero.team:
                hero.attack_target = target
                hero.move_target = None
                hero.windup_timer = 0.0
                hero.windup_target = None

        elif ctype == "stop":
            hero.move_target = None
            hero.attack_target = None
            hero.windup_timer = 0.0
            hero.windup_target = None

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
                hero.windup_timer = 0.0
                hero.windup_target = None

        elif ctype == "buy":
            self._buy_item(player, str(cmd.get("item", "")))

        elif ctype == "sell":
            item_id = str(cmd.get("item", ""))
            if item_id in player.items:
                item = self.items_data.get(item_id)
                refund = int(item.get("cost", 0) * 0.5) if item else 0
                player.items.remove(item_id)
                self._add_gold(player, refund, reliable=False)
                self._recompute_hero(player, heal=False)
                self.events.append({
                    "kind": "sold",
                    "player": player.player_id,
                    "item": item_id,
                    "amount": refund,
                })

        elif ctype == "cast":
            self._cast_ability(player, cmd)

        elif ctype == "use_item":
            self._use_item(player, cmd)

        elif ctype == "talent":
            try:
                level = int(cmd.get("level", 0))
                choice = int(cmd.get("choice", -1))
            except (TypeError, ValueError):
                return
            self._choose_talent(player, level, choice)

        elif ctype == "training":
            self.training = bool(cmd.get("enabled", True))

    def _shop_error(self, player: "PlayerState", message: str) -> None:
        self.events.append({
            "kind": "shop_error",
            "player": player.player_id,
            "message": message,
        })

    def _spend_gold(self, player: "PlayerState", cost: float) -> bool:
        reliable, unreliable, ok = formulas.spend_gold(
            player.reliable_gold, player.unreliable_gold, cost
        )
        if not ok:
            return False
        player.reliable_gold = reliable
        player.unreliable_gold = unreliable
        player.gold = reliable + unreliable
        return True

    def _add_gold(self, player: "PlayerState", amount: float, reliable: bool) -> None:
        amount = max(0.0, float(amount))
        if reliable:
            player.reliable_gold += amount
        else:
            player.unreliable_gold += amount
        player.gold = player.reliable_gold + player.unreliable_gold

    def _buy_item(self, player: "PlayerState", item_id: str) -> None:
        item = self.items_data.get(item_id)
        if not item:
            return
        if item.get("unique") and item_id in player.items:
            self._shop_error(player, "Этот предмет уже куплен")
            return
        if item.get("team_limit"):
            counts = self.team_agha if item.get("agha") else self.team_shard
            if counts.get(player.team, 0) >= int(item["team_limit"]):
                self._shop_error(player, "Лимит команды исчерпан")
                return
        if not item.get("agha") and not item.get("shard") and len(player.items) >= 6:
            self._shop_error(player, "Инвентарь полон")
            return

        cost = int(item.get("cost", 0))
        if not self.training and player.gold < cost:
            self._shop_error(player, "Недостаточно золота")
            return

        base = self.bases.get(player.team)
        at_base = not base or dist(player.hero.pos, base) <= self.shop_radius
        courier = None
        if not at_base:
            courier = next(
                (u for u in self.units if u.kind == "courier"
                 and u.owner_player == player.player_id and u.alive),
                None,
            )
            if courier is None:
                self._shop_error(player, "Нужно быть у базы или иметь курьера")
                return

        if not self.training:
            self._spend_gold(player, cost)

        if item.get("agha"):
            player.has_agha = True
            self.team_agha[player.team] += 1
        elif item.get("shard"):
            player.has_shard = True
            self.team_shard[player.team] += 1
        elif at_base:
            if item.get("recipe"):
                for component in item["recipe"]:
                    if component in player.items:
                        player.items.remove(component)
                        break
            player.items.append(item_id)
        else:
            courier.carrying.append(item_id)
            cost = 0

        self._recompute_hero(player, heal=True)
        self.events.append({
            "kind": "purchase",
            "player": player.player_id,
            "item": item_id,
            "gold": int(player.gold),
            "courier": bool(courier),
        })

    def _use_item(self, player: "PlayerState", cmd: dict) -> None:
        item_id = str(cmd.get("item", ""))
        if item_id not in player.items:
            return
        item = self.items_data.get(item_id)
        if not item or not item.get("active"):
            return
        if player.hero.item_mute_timer > 0:
            self._shop_error(player, "Предметы немы")
            return
        active = item["active"]
        cooldown = float(active.get("cooldown", 10.0))
        if player.item_cooldowns.get(item_id, 0.0) > 0:
            return
        mana = float(active.get("mana", 0.0))
        if player.mana < mana:
            return
        effect = active.get("effect")
        hero = player.hero
        used = False

        if effect == "restore":
            hero.hp = min(hero.max_hp, hero.hp + float(active.get("hp", 0)))
            player.mana = min(player.max_mana,
                              player.mana + float(active.get("mana_restore", 0)))
            used = True
        elif effect == "blood_mana":
            hp_cost = float(active.get("hp_cost", 0))
            if hero.hp > hp_cost:
                hero.hp -= hp_cost
                player.mana = min(player.max_mana,
                                  player.mana + float(active.get("mana_restore", 0)))
                used = True
        elif effect == "magic_immune":
            hero.magic_immune_timer = float(active.get("duration", 5.0))
            used = True
        elif effect == "blink":
            try:
                x = float(cmd.get("x", hero.pos[0]))
                y = float(cmd.get("y", hero.pos[1]))
            except (TypeError, ValueError):
                return
            if dist(hero.pos, (x, y)) <= float(active.get("range", 6.0)):
                hero.pos = (max(0.0, min(self.grid_w, x)),
                            max(0.0, min(self.grid_h, y)))
                hero.move_target = None
                used = True
        elif effect == "hex":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                target = None
            if target and target.alive and target.team != hero.team:
                if dist(hero.pos, target.pos) <= float(active.get("range", 5.0)):
                    target.apply_silence(float(active.get("duration", 3.0)))
                    target.apply_root(float(active.get("duration", 3.0)))
                    target.apply_item_mute(float(active.get("duration", 3.0)))
                    used = True
        elif effect == "frost_nova":
            self._aoe_damage(hero, hero.pos[0], hero.pos[1],
                             float(active.get("radius", 4.0)), 0.0,
                             float(active.get("slow", 0.45)),
                             float(active.get("duration", 3.0)))
            used = True
        elif effect == "invisibility":
            hero.apply_invisibility(float(active.get("duration", 5.0)))
            used = True
        elif effect == "damage":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                target = None
            if target and target.alive and target.team != hero.team:
                target.take_damage(float(active.get("damage", 0)), attacker=hero,
                                   damage_type=str(active.get("damage_type", "magical")))
                used = True

        if not used:
            return
        player.mana -= mana
        player.item_cooldowns[item_id] = cooldown
        self.events.append({
            "kind": "item_active",
            "player": player.player_id,
            "item": item_id,
            "x": hero.pos[0],
            "y": hero.pos[1],
        })

    def _aoe_damage(self, caster: Unit, x: float, y: float, radius: float,
                    damage: float, slow: Optional[float] = None,
                    slow_duration: float = 0.0,
                    armor_reduce: float = 0.0,
                    armor_duration: float = 0.0,
                    damage_type: str = "magical") -> None:
        dealt = 0.0
        for unit in self.units:
            if not unit.alive or unit.team == caster.team:
                continue
            if dist(unit.pos, (x, y)) <= radius:
                unit.take_damage(damage, attacker=caster, damage_type=damage_type)
                dealt += damage
                if slow:
                    duration = slow_duration
                    if caster.innate_type == "slow_duration":
                        duration += caster.innate_value
                    unit.apply_slow(slow, duration)
                if armor_reduce:
                    unit.apply_armor_break(armor_reduce, armor_duration)
                if caster.spell_burn > 0:
                    unit.take_damage(caster.spell_burn, attacker=caster,
                                     damage_type="magical")
        if dealt > 0 and caster.innate_type == "spell_lifesteal":
            caster.hp = min(caster.max_hp, caster.hp + dealt * caster.innate_value)

    def _choose_talent(self, player: "PlayerState", level: int, choice: int) -> None:
        if level not in player.pending_talents:
            return
        offers = player.talent_offers.get(level, [])
        if not (0 <= choice < len(offers)):
            return
        player.talent_choices[level] = choice
        player.pending_talents.remove(level)
        self._recompute_hero(player, heal=True)
        self.events.append({
            "kind": "talent",
            "player": player.player_id,
            "level": level,
            "choice": choice,
            "name": offers[choice].get("name", ""),
        })

    def _add_soul_stack(self, player: "PlayerState") -> None:
        """Пассивка S: +1 душа за убитое существо, до лимита."""
        cfg = self.heroes.get(player.hero_id, {})
        passive = cfg.get("passive") or {}
        if passive.get("type") != "soul_harvest":
            return
        max_souls = int(passive.get("max_souls", 20))
        if player.soul_stacks >= max_souls:
            return
        player.soul_stacks += 1
        # Пересчитываем урон, но не лечим героя.
        self._recompute_hero(player)

    def _schedule_soul_burst(self, player: "PlayerState", ability: dict) -> None:
        passive = self.heroes.get(player.hero_id, {}).get("passive") or {}
        max_souls = int(passive.get("max_souls", 20))
        souls = max(0, min(max_souls, player.soul_stacks))
        lines = max(1, int(ability.get("lines", 18)))
        damage = (
            float(ability.get("damage", 40))
            + souls * float(ability.get("damage_per_soul", 2.5))
        ) * (1.0 + max(0.0, player.hero.spell_amp))
        delay = float(ability.get("delay", 0.9))
        self.pending_bursts.append({
            "player": player.player_id,
            "timer": delay,
            "souls": lines,
            "damage": damage,
            "slow": ability.get("slow"),
            "slow_duration": float(ability.get("slow_duration", 0.0)),
        })
        # Shadow Fiend на время подготовки ультимейта стоит на месте.
        player.hero.cast_lock_timer = delay

    def _update_pending_bursts(self, dt: float) -> None:
        for item in list(self.pending_bursts):
            item["timer"] -= dt
            if item["timer"] > 0.0:
                continue
            self.pending_bursts.remove(item)

            player = self.players.get(item["player"])
            if not player or not player.hero.alive or player.hero.stun_timer > 0:
                continue

            hero = player.hero
            count = max(1, int(item["souls"]))
            for i in range(count):
                angle = (2.0 * math.pi * i) / count
                self.souls.append(SoulProjectile(
                    pos=hero.pos,
                    vel=(math.cos(angle), math.sin(angle)),
                    dmg=float(item["damage"]),
                    team=hero.team,
                    owner=hero,
                    slow=item.get("slow"),
                    slow_duration=float(item.get("slow_duration", 0.0)),
                ))

            self.events.append({
                "kind": "soul_burst",
                "player": player.player_id,
                "x": hero.pos[0],
                "y": hero.pos[1],
                "count": count,
                "color": [205, 125, 255],
            })

    def _cast_ability(self, player: "PlayerState", cmd: dict) -> None:
        hero = player.hero
        abilities = self.heroes[player.hero_id].get("abilities", [])
        try:
            slot = int(cmd.get("slot", -1))
        except (TypeError, ValueError):
            return
        if slot < 0 or slot >= len(abilities):
            return

        if hero.cast_lock_timer > 0 or hero.stun_timer > 0:
            return
        if hero.silence_timer > 0 or hero.fear_timer > 0:
            return

        base_ability = abilities[slot]
        rank = formulas.ability_rank(player.level)
        agha = bool(slot == 3 and player.has_agha)
        ability = formulas.scaled_ability(base_ability, rank, agha=agha)
        if slot == 0 and player.has_shard:
            ability["cooldown"] = float(ability.get("cooldown", 5.0)) * 0.75
            ability["mana"] = float(ability.get("mana", 0)) * 0.80
        if player.cooldowns.get(slot, 0.0) > 0:
            return
        cost = float(ability.get("mana", 0))
        if player.mana < cost:
            return

        atype = ability.get("type")
        x, y = hero.pos
        used = False
        amp = 1.0 + max(0.0, hero.spell_amp)
        damage = float(ability.get("damage", 0.0)) * amp
        damage_type = str(ability.get("damage_type", "magical"))

        if atype == "target_damage":
            try:
                target = self.get_unit(int(cmd.get("target", -1)))
            except (TypeError, ValueError):
                return
            if not target or not target.alive or target.team == hero.team:
                return
            if dist(hero.pos, target.pos) > float(ability.get("range", 5.0)) + 0.01:
                return
            target.take_damage(damage, attacker=hero, damage_type=damage_type)
            if ability.get("slow"):
                duration = float(ability.get("slow_duration", 2.0))
                if hero.innate_type == "slow_duration":
                    duration += hero.innate_value
                target.apply_slow(float(ability["slow"]), duration)
            if hero.spell_burn > 0:
                target.take_damage(hero.spell_burn, attacker=hero,
                                   damage_type="magical")
            if hero.innate_type == "spell_lifesteal":
                hero.hp = min(hero.max_hp, hero.hp + damage * hero.innate_value)
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
                damage,
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
                float(ability.get("armor_reduce", 0.0)),
                float(ability.get("armor_duration", 0.0)),
                damage_type,
            )
            used = True

        elif atype == "raze":
            # Как Shadowraze: область всегда на фиксированной дистанции
            # впереди героя, по направлению его взгляда. Клик не нужен.
            fx, fy = hero.facing
            offset = float(ability.get("offset", 2.0))
            x = hero.pos[0] + fx * offset
            y = hero.pos[1] + fy * offset
            self._aoe_damage(
                hero, x, y,
                float(ability.get("radius", 1.35)),
                damage,
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
                float(ability.get("armor_reduce", 0.0)),
                float(ability.get("armor_duration", 0.0)),
                damage_type,
            )
            used = True

        elif atype == "aoe_offset":
            # Область появляется на фиксированном расстоянии в сторону клика.
            try:
                ax = float(cmd.get("x", hero.pos[0]))
                ay = float(cmd.get("y", hero.pos[1]))
            except (TypeError, ValueError):
                return
            aim_d = dist(hero.pos, (ax, ay))
            if aim_d > float(ability.get("range", 6.0)) + 0.01:
                return
            if aim_d < 0.001:
                dx, dy = 1.0, 0.0
            else:
                dx = (ax - hero.pos[0]) / aim_d
                dy = (ay - hero.pos[1]) / aim_d
            offset = float(ability.get("offset", 2.0))
            x = hero.pos[0] + dx * offset
            y = hero.pos[1] + dy * offset
            self._aoe_damage(
                hero, x, y,
                float(ability.get("radius", 2.0)),
                damage,
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
                float(ability.get("armor_reduce", 0.0)),
                float(ability.get("armor_duration", 0.0)),
                damage_type,
            )
            used = True

        elif atype == "aoe_self":
            x, y = hero.pos
            self._aoe_damage(
                hero, x, y,
                float(ability.get("radius", 2.0)),
                damage,
                ability.get("slow"),
                float(ability.get("slow_duration", 0.0)),
                float(ability.get("armor_reduce", 0.0)),
                float(ability.get("armor_duration", 0.0)),
                damage_type,
            )
            used = True

        elif atype == "soul_burst":
            x, y = hero.pos
            self._schedule_soul_burst(player, ability)
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
            if self.training:
                player.unreliable_gold += 1000.0 * dt
                player.gold = player.reliable_gold + player.unreliable_gold
                player.cooldowns.clear()
                player.item_cooldowns.clear()
            elif in_game:
                rate = formulas.passive_gold_per_second(self.match_time)
                if rate > 0:
                    self._add_gold(player, rate * dt, reliable=False)
            player.mana = min(player.max_mana, player.mana + self.mana_regen * dt)
            for slot in list(player.cooldowns):
                player.cooldowns[slot] = max(0.0, player.cooldowns[slot] - dt)
            for item_id in list(player.item_cooldowns):
                player.item_cooldowns[item_id] = max(
                    0.0, player.item_cooldowns[item_id] - dt
                )

        for team in self.team_buffs:
            old_buff = self.team_buffs[team]
            self.team_buffs[team] = max(0.0, old_buff - dt)
            if old_buff > 0 and self.team_buffs[team] <= 0:
                for player in self.players.values():
                    if player.team == team:
                        self._recompute_hero(player)

        # Волны крипов: первая на 0:00, дальше каждые 30 секунд.
        if in_game:
            self.creep_timer += dt
            while self.creep_timer >= self.creep_interval:
                self.creep_timer -= self.creep_interval
                self._spawn_creep_wave()

        # Отложенные ультимейты (Реквием душ).
        self._update_pending_bursts(dt)

        # Рунные таймеры, босс, курьеры и стаки лагерей.
        if in_game:
            self._update_runes(dt)
            self._update_boss(dt)
            self._track_neutral_damage()
            self._update_camp_stacks()
        self._update_couriers(dt)

        # Юниты.
        for unit in list(self.units):
            if unit.alive:
                unit.update(dt, self.units, self.projectiles, self.events)

        # Проектилям и душам нужен uid для снапшотов.
        for proj in self.projectiles:
            if proj.uid == 0:
                proj.uid = self.new_uid()
        for soul in self.souls:
            if soul.uid == 0:
                soul.uid = self.new_uid()

        # Коллизии.
        for i in range(len(self.units)):
            for j in range(i + 1, len(self.units)):
                u1 = self.units[i]
                u2 = self.units[j]
                if u1.alive and u2.alive and dist(u1.pos, u2.pos) < (u1.radius + u2.radius):
                    u1.resolve_collision(u2)

        # Снаряды.
        for proj in self.projectiles:
            proj.update(dt, self.units)
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Души S: летят сквозь всех, но каждого юнита бьют один раз.
        for soul in self.souls:
            soul.update(dt, self.units)
        self.souls = [s for s in self.souls if s.alive]

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
                if unit.is_boss:
                    self._on_boss_death(unit)
                else:
                    self._queue_neutral_respawn(unit)
            elif unit.kind == "courier":
                unit.courier_respawn = formulas.COURIER_RESPAWN
            elif unit.gold_bounty > 0 or unit.xp_bounty > 0:
                self._on_unit_death(unit)

        # Респавн героев и нейтралов.
        self._update_respawns(dt)
        self._update_neutral_respawns(dt)

        # Мёртвые герои остаются для респавна, мёртвые троны — как руины.
        self.units = [
            u for u in self.units
            if u.alive or u.kind in ("hero", "throne", "courier")
        ]

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

        # Штраф за смерть: золото и 10% накопленного опыта.
        self._spend_gold(player, formulas.death_gold_penalty(player.level))
        player.xp = max(0.0, player.xp - formulas.death_xp_penalty(player.xp))

        killer = unit.last_hit_by
        if killer and killer.owner_player in self.players:
            if killer.owner_player != unit.owner_player:
                killer_player = self.players[killer.owner_player]
                killer_player.kills += 1
                self._add_soul_stack(killer_player)

                # Золото за убийство героя получает добивший.
                hero_gold = int(
                    self.hero_kill_gold_base
                    + player.level * self.hero_kill_gold_per_level
                )
                self._add_gold(killer_player, hero_gold, reliable=True)
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

        # Опыт за убийство героя получают все вражеские герои рядом,
        # помощники — 50% независимо от дистанции.
        hero_xp = formulas.hero_kill_xp(player.level)
        awarded = set()
        for other in self.players.values():
            if other.team == player.team or not other.hero.alive:
                continue
            if dist(other.hero.pos, unit.pos) <= self.xp_radius:
                self._add_xp(other, hero_xp)
                awarded.add(other.player_id)
        for pid in list(unit.damage_contributors):
            if pid in self.players and pid not in awarded and pid != unit.owner_player:
                other = self.players[pid]
                if other.hero.alive:
                    self._add_xp(other, formulas.assist_xp(hero_xp))
        unit.damage_contributors.clear()

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

    def _maybe_drop_neutral_item(self, player: "PlayerState") -> None:
        if self.match_time < 900.0 or len(player.neutral_items) >= 1:
            return
        tier = 1
        if self.match_time >= 2100.0:
            tier = 3
        elif self.match_time >= 1500.0:
            tier = 2
        candidates = [
            item_id for item_id, item in self.neutral_items_data.items()
            if int(item.get("neutral_tier", 0)) == tier
            and item_id not in player.neutral_items
        ]
        if not candidates:
            return
        if self.rng.random() > 0.05:
            return
        item_id = self.rng.choice(candidates)
        player.neutral_items.append(item_id)
        self._recompute_hero(player, heal=True)
        self.events.append({
            "kind": "neutral_item",
            "player": player.player_id,
            "item": item_id,
            "tier": tier,
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
            elif unit.kind == "tower":
                for teammate in self.players.values():
                    if teammate.team == player.team:
                        self._add_gold(teammate, 250.0, reliable=True)
                self.events.append({
                    "kind": "tower_gold",
                    "team": player.team,
                    "amount": 250,
                    "x": unit.pos[0],
                    "y": unit.pos[1],
                })
            elif unit.gold_bounty > 0:
                self._add_gold(player, unit.gold_bounty, reliable=False)
                player.cs += 1
                if unit.kind in ("creep", "creep_ranged", "neutral"):
                    self._add_soul_stack(player)
                if unit.kind == "neutral" and not unit.is_boss:
                    self._maybe_drop_neutral_item(player)
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

            if player.level in (10, 15, 20):
                meta = self._hero_meta(player)
                offers = meta.get("talents", {}).get(str(player.level), [])
                if offers and player.level not in player.talent_choices \
                        and player.level not in player.pending_talents:
                    player.pending_talents.append(player.level)
                    player.talent_offers[player.level] = offers

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
            hero.cast_lock_timer = 0.0
            hero.windup_timer = 0.0
            hero.windup_target = None
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
                "boss": u.is_boss,
                "phase": u.boss_phase,
                "courier_hits": u.courier_hits,
                "carrying": list(u.carrying),
            }
            if u.kind == "hero":
                entry.update({
                    "dmg": round(u.atk_dmg, 1),
                    "speed": u.speed,
                    "armor": round(u.armor, 2),
                    "magic_resist": round(u.magic_resist, 3),
                    "slow": u.slow_mult < 0.999,
                    "stunned": u.stun_timer > 0,
                    "silenced": u.silence_timer > 0,
                    "rooted": u.root_timer > 0,
                    "feared": u.fear_timer > 0,
                    "magic_immune": u.magic_immune_timer > 0,
                    "invisible": u.invisible_timer > 0,
                    "facing": [round(u.facing[0], 3), round(u.facing[1], 3)],
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
        projectiles.extend(
            {
                "id": s.uid,
                "x": round(s.pos[0], 3),
                "y": round(s.pos[1], 3),
                "r": 7,
                "color": list(s.color),
            }
            for s in self.souls
        )

        players = {
            pid: {
                "team": p.team,
                "name": p.name,
                "hero_id": p.hero_id,
                "gold": int(p.gold),
                "reliable_gold": int(p.reliable_gold),
                "unreliable_gold": int(p.unreliable_gold),
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
                "cooldowns": {
                    str(slot): round(cd, 2) for slot, cd in p.cooldowns.items()
                },
                "respawn": round(p.respawn_timer, 2),
                "souls": p.soul_stacks,
                "items": list(p.items),
                "neutral_items": list(p.neutral_items),
                "item_cooldowns": {
                    key: round(value, 2) for key, value in p.item_cooldowns.items()
                },
                "talents": {str(k): v for k, v in p.talent_choices.items()},
                "pending_talents": list(p.pending_talents),
                "has_agha": p.has_agha,
                "has_shard": p.has_shard,
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
            "runes": [
                {
                    "kind": r["kind"],
                    "x": round(r["pos"][0], 2),
                    "y": round(r["pos"][1], 2),
                    "active": r["active"],
                    "timer": round(r["timer"], 1),
                }
                for r in self.runes
            ],
            "boss": {
                "alive": bool(self.boss and self.boss.alive),
                "respawn": round(self.boss_respawn_timer, 1),
                "phase": self.boss.boss_phase if self.boss else 0,
            },
            "team_buffs": {team: round(value, 1) for team, value in self.team_buffs.items()},
        }
