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

        for u in self.game.units:
            if not u.alive:
                continue
            px, py = self.world_to_minimap(u.pos[0], u.pos[1])
            sx, sy = int(mx + px), int(my + py)
            if u.kind == "hero":
                pygame.draw.circle(surface, self.mm_colors["hero"], (sx, sy), 4)
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
        cs_text = self.cs_font.render(f"Крипы: {self.game.cs}", True, (220, 220, 220))
        surface.blit(cs_text, (cx + 10, cy + 8))

        # Таймер (сверху по центру)
        m = int(self.game.match_time // 60)
        s = int(self.game.match_time % 60)
        timer_text = f"{m:02d}:{s:02d}"
        timer_surf = self.big_font.render(timer_text, True, self.colors["text"])
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

        self.draw_hero_panel(surface)

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

    def draw_hero_panel(self, surface):
        sw, sh = surface.get_size()
        panel_w = 420
        panel_h = 80
        px = sw // 2 - panel_w // 2
        py = sh - panel_h - 10

        pygame.draw.rect(surface, (15, 20, 28), (px, py, panel_w, panel_h), border_radius=8)
        pygame.draw.rect(surface, (80, 90, 110), (px, py, panel_w, panel_h), 2, border_radius=8)

        hero = self.game.hero
        if hero is None:
            return

        icon_rect = (px + 10, py + 15, 50, 50)
        pygame.draw.rect(surface, self.colors["hero"], icon_rect, border_radius=4)
        pygame.draw.rect(surface, (0, 0, 0), icon_rect, 2, border_radius=4)

        # Бейдж уровня на иконке героя.
        level = int(getattr(self.game, "level", 1))
        badge_center = (px + 57, py + 62)
        pygame.draw.circle(surface, (15, 20, 28), badge_center, 11)
        pygame.draw.circle(surface, (255, 215, 0), badge_center, 11, 2)
        lvl_surf = self.small_font.render(str(level), True, (255, 255, 255))
        surface.blit(lvl_surf, (
            badge_center[0] - lvl_surf.get_width() // 2,
            badge_center[1] - lvl_surf.get_height() // 2,
        ))

        bar_x = px + 75
        bar_y = py + 15
        bar_w = 330
        bar_h = 20

        pygame.draw.rect(surface, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        hp_frac = max(0.0, min(1.0, hero.hp / max(1.0, hero.max_hp)))
        bar_color = (70, 200, 90) if getattr(hero, "alive", True) else (110, 110, 110)
        pygame.draw.rect(surface, bar_color, (bar_x, bar_y, int(bar_w * hp_frac), bar_h), border_radius=3)

        hp_text = f"{int(hero.hp)} / {int(hero.max_hp)}"
        hp_surf = self.stat_font.render(hp_text, True, (255, 255, 255))
        surface.blit(hp_surf, (bar_x + bar_w // 2 - hp_surf.get_width() // 2, bar_y + 4))

        # Полоска опыта.
        xp_y = bar_y + bar_h + 4
        xp_h = 5
        pygame.draw.rect(surface, (30, 30, 30), (bar_x, xp_y, bar_w, xp_h), border_radius=2)
        xp = float(getattr(self.game, "xp", 0.0))
        xp_next = max(1.0, float(getattr(self.game, "xp_next", 100.0)))
        xp_frac = max(0.0, min(1.0, xp / xp_next))
        if level >= int(getattr(self.game, "max_level", 10)):
            xp_frac = 1.0
        pygame.draw.rect(
            surface, (110, 150, 255),
            (bar_x, xp_y, int(bar_w * xp_frac), xp_h), border_radius=2,
        )

        stats = [
            ("Урон", str(int(hero.atk_dmg)), (255, 100, 100)),
            ("Скор.", str(int(hero.speed * 10)), (100, 200, 255)),
            ("Броня", str(int(hero.armor)), (200, 200, 200)),
        ]

        stat_x = bar_x
        stat_y = py + 47

        for i, (label, value, color) in enumerate(stats):
            pygame.draw.circle(surface, color, (stat_x + 8 + i * 110, stat_y + 8), 6)
            text = self.stat_font.render(f"{label}: {value}", True, (200, 200, 200))
            surface.blit(text, (stat_x + 20 + i * 110, stat_y))

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