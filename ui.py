import math

import pygame
from typing import Tuple


class FloatingText:
    def __init__(self, text: str, pos: Tuple[float, float], color: Tuple[int, int, int],
                 lifetime: float = 0.8, vy: float = -40.0, vx: float = 0.0):
        self.text = text
        self.pos = pos
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.vy = vy
        self.vx = vx

    def update(self, dt):
        self.lifetime -= dt
        self.pos = (self.pos[0] + self.vx * dt, self.pos[1] + self.vy * dt)


class UI:
    def __init__(self, game):
        self.game = game
        self.cfg = game.cfg
        self.colors = game.colors
        self.screen = game.screen

        self.font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("consolas", 10)
        self.big_font = pygame.font.SysFont("consolas", 20, bold=True)
        self.huge_font = pygame.font.SysFont("consolas", 46, bold=True)
        self.gold_font = pygame.font.SysFont("consolas", 24, bold=True)
        self.cs_font = pygame.font.SysFont("consolas", 18, bold=True)
        self.popup_font = pygame.font.SysFont("consolas", 16, bold=True)
        self.stat_font = pygame.font.SysFont("consolas", 12)
        self.mid_font = pygame.font.SysFont("consolas", 13)
        self.fps_font = pygame.font.SysFont("consolas", 14, bold=True)

        mm = self.cfg["minimap"]
        self.mm_size = mm["size"]
        self.mm_margin = mm["margin"]
        self.mm_bg = tuple(mm["bg"])
        self.mm_border = tuple(mm["border"])
        self.mm_camera = tuple(mm["camera_rect"])
        self.mm_colors = {
            "hero": tuple(mm["hero"]),
            "creep_a": tuple(mm["creep_a"]),
            "creep_b": tuple(mm["creep_b"]),
            "tower_a": tuple(mm["tower_a"]),
            "tower_b": tuple(mm["tower_b"]),
            "lane": tuple(mm["lane"]),
        }
        self.shop_rects = {}

    def _fit_text(self, text, font, max_width: int) -> str:
        text = str(text)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix

    def world_to_minimap(self, gx: float, gy: float) -> Tuple[float, float]:
        px = gx / self.game.Grid.grid_w * self.mm_size
        py = gy / self.game.Grid.grid_h * self.mm_size
        return px, py

    def draw_minimap(self, surface):
        sw, sh = surface.get_size()
        mx = self.mm_margin
        my = sh - self.mm_size - self.mm_margin

        pygame.draw.rect(surface, self.mm_bg, (mx, my, self.mm_size, self.mm_size))
        pygame.draw.rect(surface, self.mm_border, (mx, my, self.mm_size, self.mm_size), 2)

        # Река на миникарте (та же диагональ, что и в мире).
        rx1, ry1 = self.world_to_minimap(0, 0)
        rx2, ry2 = self.world_to_minimap(self.game.Grid.grid_w, self.game.Grid.grid_h)
        pygame.draw.line(
            surface, self.colors.get("river", (28, 86, 132)),
            (mx + rx1, my + ry1), (mx + rx2, my + ry2), 6,
        )

        for path in self.game.lanes.values():
            pts = []
            for gx, gy in path:
                px, py = self.world_to_minimap(gx, gy)
                pts.append((mx + px, my + py))
            if len(pts) >= 2:
                pygame.draw.lines(surface, self.mm_colors["lane"], False, pts, 2)

        for team in ("A", "B"):
            gx, gy = self.game.bases[team]
            px, py = self.world_to_minimap(gx, gy)
            color = self.colors["base_a"] if team == "A" else self.colors["base_b"]
            pygame.draw.circle(surface, color, (int(mx + px), int(my + py)), 5)

        for rx, ry in self.game.map_cfg.get("runes", []):
            px, py = self.world_to_minimap(rx, ry)
            pygame.draw.circle(surface, (170, 235, 255), (int(mx + px), int(my + py)), 3)
            pygame.draw.circle(surface, (90, 170, 220), (int(mx + px), int(my + py)), 3, 1)

        for u in self.game.units:
            if not u.alive:
                continue
            px, py = self.world_to_minimap(u.pos[0], u.pos[1])
            sx, sy = int(mx + px), int(my + py)
            if u.kind == "hero":
                pygame.draw.circle(surface, self.mm_colors["hero"], (sx, sy), 4)
            elif u.kind == "neutral":
                pygame.draw.circle(surface, (210, 180, 120), (sx, sy), 2)
            elif u.kind == "throne":
                col = self.colors["base_a"] if u.team == "A" else self.colors["base_b"]
                pygame.draw.rect(surface, col, (sx - 4, sy - 4, 8, 8))
                pygame.draw.rect(surface, (255, 215, 0), (sx - 4, sy - 4, 8, 8), 1)
            elif u.kind == "tower":
                col = self.mm_colors["tower_a"] if u.team == "A" else self.mm_colors["tower_b"]
                pygame.draw.rect(surface, col, (sx - 2, sy - 2, 4, 4))
            else:
                col = self.mm_colors["creep_a"] if u.team == "A" else self.mm_colors["creep_b"]
                pygame.draw.circle(surface, col, (sx, sy), 2)

        corners = [(0, 0), (sw, 0), (sw, sh), (0, sh)]
        gxs, gys = [], []
        for sx, sy in corners:
            wx = sx + self.game.camera.x
            wy = sy + self.game.camera.y
            gx, gy = self.game.Grid.to_grid(wx, wy)
            gxs.append(gx)
            gys.append(gy)

        min_gx, max_gx = min(gxs), max(gxs)
        min_gy, max_gy = min(gys), max(gys)
        min_gx = max(0, min_gx); max_gx = min(self.game.Grid.grid_w, max_gx)
        min_gy = max(0, min_gy); max_gy = min(self.game.Grid.grid_h, max_gy)

        x1, y1 = self.world_to_minimap(min_gx, min_gy)
        x2, y2 = self.world_to_minimap(max_gx, max_gy)
        pygame.draw.rect(surface, self.mm_camera,
                         (int(mx + x1), int(my + y1),
                          int(x2 - x1), int(y2 - y1)), 1)

    def draw_hud(self, surface):
        sw, sh = surface.get_size()

        # Золото (справа снизу)
        rect_w = 160
        rect_h = 40
        rx = sw - rect_w - self.mm_margin
        ry = sh - rect_h - self.mm_margin

        pygame.draw.rect(surface, (10, 14, 20), (rx, ry, rect_w, rect_h))
        pygame.draw.rect(surface, (80, 90, 110), (rx, ry, rect_w, rect_h), 2)
        pygame.draw.circle(surface, (255, 215, 0), (rx + 20, ry + 20), 10)
        pygame.draw.circle(surface, (200, 170, 0), (rx + 20, ry + 20), 7)
        gold_text = self.gold_font.render(str(self.game.gold), True, (255, 255, 255))
        surface.blit(gold_text, (rx + 40, ry + 8))

        # Счетчик CS (справа сверху)
        cs_rect_w = 140
        cs_rect_h = 36
        cx = sw - cs_rect_w - self.mm_margin
        cy = 8
        pygame.draw.rect(surface, (10, 14, 20), (cx, cy, cs_rect_w, cs_rect_h))
        pygame.draw.rect(surface, (80, 90, 110), (cx, cy, cs_rect_w, cs_rect_h), 2)
        cs_text = self.cs_font.render(
            f"CS {self.game.cs} / D {self.game.denies}", True, (220, 220, 220)
        )
        surface.blit(cs_text, (cx + 10, cy + 8))

        # Таймер (сверху по центру). До 0:00 показываем обратный отсчёт.
        t = float(self.game.match_time)
        if t < 0:
            remaining = int(math.ceil(-t))
            timer_text = f"-{remaining // 60:02d}:{remaining % 60:02d}"
            timer_color = (255, 220, 140)
        else:
            timer_text = f"{int(t // 60):02d}:{int(t % 60):02d}"
            timer_color = self.colors["text"]
        timer_surf = self.big_font.render(timer_text, True, timer_color)
        tw = timer_surf.get_width()
        pygame.draw.rect(surface, (10, 14, 20), (sw // 2 - tw // 2 - 12, 8, tw + 24, 32))
        pygame.draw.rect(surface, (80, 90, 110), (sw // 2 - tw // 2 - 12, 8, tw + 24, 32), 2)
        surface.blit(timer_surf, (sw // 2 - tw // 2, 14))

        # Сетевая информация (слева сверху)
        if getattr(self.game, "net_mode", False):
            if getattr(self.game, "disconnected", False):
                net_text = "DISCONNECTED"
                net_color = (255, 110, 110)
            else:
                net_text = f"LAN  ping {getattr(self.game, 'ping_ms', 0)} ms"
                net_color = (150, 220, 255)

            net_surf = self.fps_font.render(net_text, True, net_color)
            net_rect = (8, 8, net_surf.get_width() + 16, 28)
            pygame.draw.rect(surface, (10, 14, 20), net_rect)
            pygame.draw.rect(surface, (80, 90, 110), net_rect, 2)
            surface.blit(net_surf, (16, 13))

        # Ожидание второго игрока
        if getattr(self.game, "net_mode", False):
            online = getattr(self.game, "online_players", 0)
            max_players = getattr(self.game, "max_players", 2)
            if 0 < online < max_players:
                wait_text = f"Ожидание игроков: {online}/{max_players}"
                wait_surf = self.font.render(wait_text, True, (255, 220, 120))
                surface.blit(wait_surf, (sw // 2 - wait_surf.get_width() // 2, 52))

        # Смерть и таймер возрождения
        hero = self.game.hero
        if hero is not None and not hero.alive:
            respawn = max(0.0, getattr(self.game, "respawn_timer", 0.0))
            dead_text = f"Возрождение через {respawn:.1f}s"
            dead_surf = self.big_font.render(dead_text, True, (255, 120, 120))
            surface.blit(dead_surf, (sw // 2 - dead_surf.get_width() // 2, sh // 2 - 20))

        status = getattr(self.game, "status_message", "")
        if status:
            status_surf = self.font.render(status, True, (225, 225, 225))
            surface.blit(status_surf, (16, 42))

        self.draw_ability_bar(surface)
        self.draw_hero_panel(surface)
        self.draw_objectives(surface)
        self.draw_talent_offer(surface)

        # FPS (слева снизу)
        if self.game.show_fps:
            fps_val = int(self.game.clock.get_fps())
            fps_text = self.fps_font.render(f"FPS: {fps_val}", True, (255, 255, 255))
            text_rect = fps_text.get_rect()
            text_rect.bottomleft = (10, sh - 10)

            pygame.draw.rect(
                surface, (10, 14, 20),
                (text_rect.x - 4, text_rect.y - 4, text_rect.width + 8, text_rect.height + 8)
            )
            pygame.draw.rect(
                surface, (80, 90, 110),
                (text_rect.x - 4, text_rect.y - 4, text_rect.width + 8, text_rect.height + 8), 1
            )

            surface.blit(fps_text, text_rect)

    def draw_death_overlay(self, surface):
        game = self.game
        if game.match_over or game.hero is None or getattr(game.hero, "alive", True):
            return
        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((40, 0, 0, 70))
        surface.blit(overlay, (0, 0))
        panel = pygame.Rect(sw // 2 - 220, sh // 2 - 70, 440, 140)
        pygame.draw.rect(surface, (20, 12, 16), panel, border_radius=10)
        pygame.draw.rect(surface, (190, 80, 80), panel, 2, border_radius=10)
        title = self.big_font.render("ВОЗРОЖДЕНИЕ", True, (255, 160, 150))
        surface.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 18))
        timer = self.gold_font.render(
            f"{max(0, int(game.respawn_timer))}", True, (255, 230, 200)
        )
        surface.blit(timer, (panel.centerx - timer.get_width() // 2, panel.y + 52))
        hint = self.small_font.render(
            "B — быстрая покупка снаряжения", True, (210, 190, 180)
        )
        surface.blit(hint, (panel.centerx - hint.get_width() // 2, panel.y + 108))

    def draw_objectives(self, surface):
        game = self.game
        sw, _ = surface.get_size()
        data = None
        if game.net_mode and game.snaps:
            data = game.snaps[-1].data
        runes = data.get("runes", []) if data else []
        boss = data.get("boss", {}) if data else {}
        if game.world is not None and not game.net_mode:
            runes = [
                {"kind": r["kind"], "active": r["active"], "timer": r["timer"]}
                for r in game.world.runes
            ]
            boss = {
                "alive": bool(game.world.boss and game.world.boss.alive),
                "respawn": game.world.boss_respawn_timer,
                "phase": game.world.boss.boss_phase if game.world.boss else 0,
            }

        lines = []
        for rune in runes:
            kind = "богатство" if rune.get("kind") == "wealth" else "мудрость"
            state = "готово" if rune.get("active") else f"{int(rune.get('timer', 0))}с"
            lines.append(f"руна {kind}: {state}")
        if boss:
            if boss.get("alive"):
                lines.append(f"босс: жив, фаза {boss.get('phase', 1)}")
            else:
                lines.append(f"босс: {int(boss.get('respawn', 0)) // 60}:{int(boss.get('respawn', 0)) % 60:02d}")

        x = sw // 2 - 190
        y = 44
        for index, line in enumerate(lines[:3]):
            text = self.small_font.render(line, True, (200, 210, 230))
            surface.blit(text, (x, y + index * 14))

    def draw_talent_offer(self, surface):
        game = self.game
        pending = getattr(game, "pending_talents", [])
        if not pending:
            return
        level = pending[0]
        meta = getattr(game, "heroes_meta", {}).get(game.hero_id, {})
        offers = meta.get("talents", {}).get(str(level), [])
        if not offers:
            return
        sw, sh = surface.get_size()
        width, height = 460, 130
        x = sw // 2 - width // 2
        y = sh // 2 - height // 2
        pygame.draw.rect(surface, (12, 18, 27), (x, y, width, height), border_radius=10)
        pygame.draw.rect(surface, (180, 140, 255), (x, y, width, height), 2, border_radius=10)
        title = self.mid_font.render(f"ТАЛАНТ {level} УРОВНЯ", True, (225, 190, 255))
        surface.blit(title, (x + 14, y + 10))
        for index, offer in enumerate(offers[:2]):
            key = "Z" if index == 0 else "X"
            name = self.mid_font.render(f"[{key}] {offer.get('name', '')}", True, (240, 235, 255))
            desc = self.small_font.render(offer.get("desc", ""), True, (175, 185, 205))
            surface.blit(name, (x + 16, y + 38 + index * 38))
            surface.blit(desc, (x + 44, y + 54 + index * 38))

    def draw_ability_bar(self, surface):
        game = self.game
        if not game.abilities or game.hero is None:
            return

        sw, sh = surface.get_size()
        abilities = game.abilities[:4]
        slot = 54
        gap = 10
        total = len(abilities) * slot + (len(abilities) - 1) * gap
        x = sw // 2 - total // 2
        y = sh - 112 - 10 - 66

        for i, ability in enumerate(abilities):
            rect = pygame.Rect(x + i * (slot + gap), y, slot, slot)
            color = tuple(ability.get("color", (180, 190, 200)))
            cost = float(ability.get("mana", 0))
            affordable = game.mana >= cost
            fill = (22, 34, 48) if affordable else (46, 28, 30)
            pygame.draw.rect(surface, fill, rect, border_radius=8)
            border = (255, 215, 110) if game.pending_ability == i else (90, 115, 150)
            pygame.draw.rect(surface, border, rect, 2, border_radius=8)
            pygame.draw.circle(surface, color, rect.center, 15)
            pygame.draw.circle(surface, (15, 20, 28), rect.center, 15, 2)

            key = ability.get("key", "?")
            key_surf = self.stat_font.render(key, True, (255, 255, 255))
            surface.blit(key_surf, (rect.x + 5, rect.y + 3))

            cooldown = game.cooldowns.get(i, 0.0)
            if cooldown > 0:
                overlay = pygame.Surface((slot, slot), pygame.SRCALPHA)
                overlay.fill((5, 8, 12, 170))
                surface.blit(overlay, rect.topleft)
                cd_surf = self.big_font.render(f"{cooldown:.0f}", True, (255, 240, 180))
                surface.blit(cd_surf, (
                    rect.centerx - cd_surf.get_width() // 2,
                    rect.centery - cd_surf.get_height() // 2,
                ))

            cost_surf = self.small_font.render(str(int(cost)), True, (150, 200, 255) if affordable else (255, 120, 120))
            surface.blit(cost_surf, (rect.right - cost_surf.get_width() - 4, rect.bottom - 13))

        hero_cfg = game.heroes.get(game.hero_id, {})
        passive = hero_cfg.get("passive") or {}
        if passive.get("type") == "soul_harvest":
            max_souls = int(passive.get("max_souls", 20))
            souls = int(getattr(game, "soul_stacks", 0))
            soul_text = self.small_font.render(
                f"ДУШИ {souls}/{max_souls}", True, (220, 160, 255),
            )
            surface.blit(
                soul_text,
                (x + total + 14, y + (slot - soul_text.get_height()) // 2),
            )

        hint = self.small_font.render(
            "Q W E R — способности    B — магазин    Alt — радиусы вышек",
            True, (150, 165, 185),
        )
        surface.blit(hint, (sw // 2 - hint.get_width() // 2, y - 14))

    def draw_hero_panel(self, surface):
        sw, sh = surface.get_size()
        panel_w = 620
        panel_h = 112
        px = sw // 2 - panel_w // 2
        py = sh - panel_h - 10

        pygame.draw.rect(surface, (15, 20, 28), (px, py, panel_w, panel_h), border_radius=8)
        pygame.draw.rect(surface, (80, 90, 110), (px, py, panel_w, panel_h), 2, border_radius=8)

        hero = self.game.hero
        if hero is None:
            return

        hero_cfg = self.game.heroes.get(self.game.hero_id, {})
        hero_color = tuple(hero_cfg.get("color", self.colors["hero"]))
        if not getattr(hero, "alive", True):
            hero_color = (95, 95, 95)

        icon_rect = pygame.Rect(px + 12, py + 14, 60, 60)
        pygame.draw.rect(surface, hero_color, icon_rect, border_radius=6)
        pygame.draw.rect(surface, (0, 0, 0), icon_rect, 2, border_radius=6)
        initial = str(hero_cfg.get("name", "?"))[:1].upper()
        init_surf = self.big_font.render(initial, True, (25, 28, 34))
        surface.blit(init_surf, (
            icon_rect.centerx - init_surf.get_width() // 2,
            icon_rect.centery - init_surf.get_height() // 2,
        ))

        level = int(getattr(self.game, "level", 1))
        badge_center = (px + 64, py + 68)
        pygame.draw.circle(surface, (15, 20, 28), badge_center, 12)
        pygame.draw.circle(surface, (255, 215, 0), badge_center, 12, 2)
        lvl_surf = self.small_font.render(str(level), True, (255, 255, 255))
        surface.blit(lvl_surf, (
            badge_center[0] - lvl_surf.get_width() // 2,
            badge_center[1] - lvl_surf.get_height() // 2,
        ))

        bar_x = px + 86
        bar_y = py + 12
        bar_w = panel_w - 104
        bar_h = 18

        pygame.draw.rect(surface, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        hp_frac = max(0.0, min(1.0, hero.hp / max(1.0, hero.max_hp)))
        bar_color = (70, 200, 90) if getattr(hero, "alive", True) else (110, 110, 110)
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, int(bar_w * hp_frac), bar_h), border_radius=3)
        hp_text = f"{int(hero.hp)} / {int(hero.max_hp)}"
        hp_surf = self.stat_font.render(hp_text, True, (255, 255, 255))
        surface.blit(hp_surf, (bar_x + bar_w // 2 - hp_surf.get_width() // 2, bar_y + 3))

        mana_y = bar_y + bar_h + 2
        mana_h = 9
        pygame.draw.rect(surface, (25, 30, 45), (bar_x, mana_y, bar_w, mana_h), border_radius=2)
        mana_frac = max(0.0, min(1.0, self.game.mana / max(1.0, self.game.max_mana)))
        pygame.draw.rect(surface, (70, 130, 230), (bar_x, mana_y, int(bar_w * mana_frac), mana_h), border_radius=2)
        mana_text = f"{int(self.game.mana)} / {int(self.game.max_mana)}"
        mana_surf = self.small_font.render(mana_text, True, (210, 225, 255))
        surface.blit(mana_surf, (bar_x + bar_w - mana_surf.get_width() - 4, mana_y - 2))

        xp_y = mana_y + mana_h + 2
        xp_h = 5
        pygame.draw.rect(surface, (30, 30, 30), (bar_x, xp_y, bar_w, xp_h), border_radius=2)
        xp = float(getattr(self.game, "xp", 0.0))
        xp_next = max(1.0, float(getattr(self.game, "xp_next", 100.0)))
        xp_frac = max(0.0, min(1.0, xp / xp_next))
        if level >= int(getattr(self.game, "max_level", 10)):
            xp_frac = 1.0
        pygame.draw.rect(surface, (150, 120, 255),
                         (bar_x, xp_y, int(bar_w * xp_frac), xp_h), border_radius=2)

        attrs = [
            ("СИЛ", int(self.game.str), (255, 150, 110)),
            ("ЛОВ", int(self.game.agi), (140, 235, 150)),
            ("ИНТ", int(self.game.int), (130, 190, 255)),
        ]
        for i, (label, value, color) in enumerate(attrs):
            x = bar_x + i * 105
            pygame.draw.circle(surface, color, (x + 5, py + 59), 5)
            text = self.stat_font.render(f"{label} {value}", True, (215, 220, 232))
            surface.blit(text, (x + 15, py + 52))

        combat = [
            ("Урон", f"{hero.atk_dmg:.0f}"),
            ("Броня", f"{hero.armor:.1f}"),
            ("Скор.", f"{hero.speed * 10:.0f}"),
            ("Дальн.", f"{hero.atk_range:.1f}"),
        ]
        for i, (label, value) in enumerate(combat):
            x = bar_x + i * 125
            text = self.stat_font.render(f"{label} {value}", True, (190, 200, 215))
            surface.blit(text, (x, py + 67))

        kda = (
            f"K/D/A {self.game.kills}/{self.game.deaths}/{self.game.assists}   "
            f"CS {self.game.cs}   Deny {self.game.denies}"
        )
        kda_surf = self.mid_font.render(kda, True, (225, 230, 240))
        surface.blit(kda_surf, (bar_x, py + 82))

        # 6 слотов инвентаря.
        slot_size = 28
        slot_gap = 4
        slots_x = bar_x + 310
        slots_y = py + 82
        for slot in range(6):
            cell = pygame.Rect(
                slots_x + slot * (slot_size + slot_gap),
                slots_y,
                slot_size,
                slot_size,
            )
            pygame.draw.rect(surface, (20, 28, 40), cell, border_radius=4)
            pygame.draw.rect(surface, (70, 90, 120), cell, 1, border_radius=4)
            if slot < len(self.game.items):
                item_id = self.game.items[slot]
                icon = self.game.item_icons.get(item_id)
                if icon is not None:
                    scaled = pygame.transform.smoothscale(icon, (24, 24))
                    surface.blit(scaled, scaled.get_rect(center=cell.center))
                else:
                    pygame.draw.rect(surface, (90, 110, 140), cell.inflate(-8, -8), border_radius=3)

        neutral = getattr(self.game, "neutral_items", [])
        if neutral:
            item = (self.game.items_data.get(neutral[0])
                    or self.game.neutral_items_data.get(neutral[0], {}))
            text = self.small_font.render(
                f"Нейтрал: {item.get('name', neutral[0])}", True, (210, 170, 255)
            )
            surface.blit(text, (bar_x + 310, py + 70))

    def draw_shop(self, surface):
        game = self.game
        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        surface.blit(overlay, (0, 0))

        width, height = 820, 500
        x = sw // 2 - width // 2
        y = sh // 2 - height // 2
        pygame.draw.rect(surface, (12, 18, 27), (x, y, width, height), border_radius=12)
        pygame.draw.rect(surface, (100, 130, 170), (x, y, width, height), 2, border_radius=12)

        title = self.big_font.render("МАГАЗИН", True, (255, 225, 140))
        surface.blit(title, (x + 20, y + 14))
        gold = self.gold_font.render(f"{game.gold}", True, (255, 215, 0))
        surface.blit(gold, (x + width - gold.get_width() - 22, y + 12))

        self.shop_rects.clear()
        items = list(game.items_data.items())
        col_w = (width - 48) // 4
        for i, (item_id, item) in enumerate(items):
            col = i % 4
            row_index = i // 4
            row = pygame.Rect(
                x + 16 + col * (col_w + 8),
                y + 50 + row_index * 41,
                col_w,
                36,
            )
            self.shop_rects[item_id] = row
            owned = game.items.count(item_id)
            can_buy = game.gold >= item.get("cost", 0) and not (item.get("unique") and owned)
            pygame.draw.rect(surface, (20, 30, 43) if can_buy else (28, 24, 28), row, border_radius=5)
            pygame.draw.rect(surface, (60, 85, 115), row, 1, border_radius=5)

            icon_rect = pygame.Rect(row.x + 4, row.y + 4, 28, 28)
            icon = game.item_icons.get(item_id)
            if icon is not None:
                scaled = pygame.transform.smoothscale(icon, (26, 26))
                surface.blit(scaled, scaled.get_rect(center=icon_rect.center))
            else:
                pygame.draw.rect(surface, (80, 100, 130), icon_rect, border_radius=4)

            name = self.small_font.render(
                self._fit_text(item.get("name", item_id), self.small_font, col_w - 74),
                True, (235, 240, 248),
            )
            surface.blit(name, (row.x + 36, row.y + 3))
            count = f" x{owned}" if owned else ""
            price_color = (255, 215, 0) if can_buy else (220, 110, 110)
            price = self.small_font.render(f"{item.get('cost', 0)}{count}", True, price_color)
            surface.blit(price, (row.x + 36, row.y + 18))
            tier = self.small_font.render(str(item.get("tier", ""))[:3], True, (130, 150, 175))
            surface.blit(tier, (row.right - tier.get_width() - 4, row.y + 10))

        hint = self.small_font.render(
            "ЛКМ — купить   Ctrl+ЛКМ — продать   B/ПКМ — закрыть", True, (150, 165, 185)
        )
        surface.blit(hint, (x + 20, y + height - 26))
        if game.shop_message:
            msg = self.mid_font.render(game.shop_message, True, (255, 210, 140))
            surface.blit(msg, (x + 280, y + height - 28))

    def shop_hit(self, pos):
        for item_id, rect in self.shop_rects.items():
            if rect.collidepoint(pos):
                return item_id
        return None

    def draw_scoreboard(self, surface):
        game = self.game
        if game.net_mode:
            players = game.snaps[-1].data.get("players", {}) if game.snaps else {}
        elif game.world is not None:
            players = {
                pid: {
                    "team": p.team,
                    "name": p.name,
                    "hero_id": p.hero_id,
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "assists": p.assists,
                    "cs": p.cs,
                    "denies": p.denies,
                    "gold": int(p.gold),
                    "level": p.level,
                    "items": list(p.items),
                }
                for pid, p in game.world.players.items()
            }
        else:
            players = {}

        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))

        width, height = 900, 430
        x = sw // 2 - width // 2
        y = sh // 2 - height // 2
        pygame.draw.rect(surface, (10, 16, 25), (x, y, width, height), border_radius=12)
        pygame.draw.rect(surface, (100, 130, 170), (x, y, width, height), 2, border_radius=12)
        title = self.big_font.render("ТАБЛИЦА", True, (255, 225, 140))
        surface.blit(title, (x + 20, y + 14))
        hint = self.small_font.render("Tab — закрыть", True, (150, 165, 185))
        surface.blit(hint, (x + width - hint.get_width() - 20, y + 20))

        teams = {"A": [], "B": []}
        for pid, player in players.items():
            team = player.get("team", "A")
            if team in teams:
                teams[team].append((pid, player))
        for team in teams:
            teams[team].sort(key=lambda item: (-int(item[1].get("kills", 0)), item[0]))

        for index, team in enumerate(("A", "B")):
            col_x = x + 24 + index * 450
            team_color = (120, 180, 255) if team == "A" else (255, 130, 120)
            label = "СИЛЫ СВЕТА" if team == "A" else "СИЛЫ ТЬМЫ"
            surface.blit(self.big_font.render(label, True, team_color), (col_x, y + 52))
            header = self.small_font.render("игрок / герой          K/D/A     CS/D   золото", True, (150, 165, 185))
            surface.blit(header, (col_x, y + 82))
            row_y = y + 104
            for pid, player in teams[team]:
                hero_id = player.get("hero_id", "")
                hero_name = game.heroes.get(hero_id, {}).get("name", hero_id)
                name = str(player.get("name", pid))
                if pid == game.player_id:
                    name += " (ты)"
                name = self._fit_text(f"{name} / {hero_name}", self.mid_font, 210)
                surface.blit(self.mid_font.render(name, True, (230, 235, 245)), (col_x, row_y))
                kda = f"{player.get('kills', 0)}/{player.get('deaths', 0)}/{player.get('assists', 0)}"
                surface.blit(self.mid_font.render(kda, True, (225, 230, 240)), (col_x + 215, row_y))
                cs = f"{player.get('cs', 0)}/{player.get('denies', 0)}"
                surface.blit(self.mid_font.render(cs, True, (200, 215, 230)), (col_x + 280, row_y))
                gold = str(player.get("gold", 0))
                surface.blit(self.mid_font.render(gold, True, (255, 215, 0)), (col_x + 330, row_y))
                items = player.get("items", [])
                if items:
                    item_text = self.small_font.render(f"{len(items)} предм.", True, (150, 180, 210))
                    surface.blit(item_text, (col_x + 365, row_y + 1))
                row_y += 42

    def draw_match_end(self, surface):
        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))

        winner = getattr(self.game, "winner", None)
        team = getattr(self.game, "team", "A")
        labels = {"A": "сил света", "B": "сил тьмы"}
        enemy = "B" if team == "A" else "A"

        if winner == team:
            title = "ПОБЕДА"
            subtitle = f"Трон {labels.get(enemy, 'врага')} разрушен"
            color = (140, 255, 160)
        elif winner is not None:
            title = "ПОРАЖЕНИЕ"
            subtitle = "Ваш трон пал"
            color = (255, 120, 120)
        else:
            title = "МАТЧ ОКОНЧЕН"
            subtitle = ""
            color = (230, 230, 230)

        title_surf = self.huge_font.render(title, True, color)
        surface.blit(title_surf, (sw // 2 - title_surf.get_width() // 2, sh // 2 - 70))

        if subtitle:
            sub_surf = self.big_font.render(subtitle, True, (235, 235, 235))
            surface.blit(sub_surf, (sw // 2 - sub_surf.get_width() // 2, sh // 2 + 5))

        hint = self.font.render("Esc — выход, ~ — консоль", True, (190, 190, 190))
        surface.blit(hint, (sw // 2 - hint.get_width() // 2, sh // 2 + 45))

    def draw_floating_texts(self, surface):
        for ft in self.game.floating_texts:
            sx = ft.pos[0] - self.game.camera.x
            sy = ft.pos[1] - self.game.camera.y

            alpha = max(0, min(255, int(255 * (ft.lifetime / ft.max_lifetime))))
            text_surf = self.popup_font.render(ft.text, True, ft.color)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, (int(sx), int(sy)))