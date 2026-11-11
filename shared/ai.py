"""Простые боты для заполнения LAN-слотов."""

from __future__ import annotations

import random
from typing import Optional

from shared.sim import World, dist


class BotController:
    def __init__(self, player_id: str, seed: Optional[int] = None):
        self.player_id = player_id
        self.rng = random.Random(seed)
        self.think_timer = 0.0

    def update(self, world: World, dt: float) -> None:
        player = world.players.get(self.player_id)
        if not player:
            return
        hero = player.hero
        if not hero.alive:
            return

        self.think_timer -= dt
        if self.think_timer > 0:
            return
        self.think_timer = 0.35 + self.rng.random() * 0.25

        enemies = [
            u for u in world.units
            if u.alive and u.team != hero.team
            and u.kind in ("hero", "creep", "creep_ranged", "tower", "neutral")
        ]
        enemy_heroes = [u for u in enemies if u.kind == "hero"]
        base = world.bases.get(hero.team)
        hp_frac = hero.hp / max(1.0, hero.max_hp)

        # Отступление.
        if hp_frac < 0.30 and base:
            world.apply_command(self.player_id, {"type": "move", "x": base[0], "y": base[1]})
            return

        # Добивание/атака ближайшей цели.
        if enemies:
            target = min(enemies, key=lambda u: dist(hero.pos, u.pos))
            if dist(hero.pos, target.pos) <= hero.atk_range + 2.5:
                world.apply_command(self.player_id, {"type": "attack", "target": target.uid})
                self._try_ability(world, player, target)
                return

        if base and dist(hero.pos, base) <= world.shop_radius:
            self._try_buy(world, player)

        enemy_base = world.bases.get("B" if hero.team == "A" else "A")
        if enemy_base:
            lane = min(
                world.lanes.values(),
                key=lambda path: min(dist(hero.pos, p) for p in path),
            )
            ahead = min(
                lane,
                key=lambda p: dist(p, enemy_base),
            )
            world.apply_command(self.player_id, {"type": "move", "x": ahead[0], "y": ahead[1]})

    def _try_ability(self, world: World, player, target) -> None:
        abilities = world.heroes[player.hero_id].get("abilities", [])
        usable = [
            slot for slot in range(len(abilities))
            if player.cooldowns.get(slot, 0.0) <= 0
            and player.mana >= float(abilities[slot].get("mana", 0))
        ]
        if not usable:
            return
        slot = self.rng.choice(usable)
        atype = abilities[slot].get("type")
        if atype == "target_damage":
            world.apply_command(
                self.player_id,
                {"type": "cast", "slot": slot, "target": target.uid},
            )
        elif atype in ("aoe_damage", "aoe_offset"):
            world.apply_command(
                self.player_id,
                {"type": "cast", "slot": slot, "x": target.pos[0], "y": target.pos[1]},
            )
        else:
            world.apply_command(self.player_id, {"type": "cast", "slot": slot})

    def _try_buy(self, world: World, player) -> None:
        if player.gold < 500:
            return
        candidates = [
            item_id for item_id, item in world.items_data.items()
            if item.get("tier") in ("base", "mid")
            and item_id not in player.items
            and int(item.get("cost", 0)) <= player.gold
        ]
        if not candidates:
            return
        world.apply_command(
            self.player_id,
            {"type": "buy", "item": self.rng.choice(candidates)},
        )


class BotManager:
    def __init__(self, world: World, player_ids, seed: int = 7):
        self.world = world
        self.bots = [
            BotController(pid, seed + index)
            for index, pid in enumerate(player_ids)
        ]

    def update(self, dt: float) -> None:
        for bot in self.bots:
            bot.update(self.world, dt)
