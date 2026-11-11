"""Меню, просмотр героев и экран лобби."""

from pathlib import Path

import pygame

import gfx

PRIMARY_LABEL = {"str": "СИЛА", "agi": "ЛОВКОСТЬ", "int": "ИНТЕЛЛЕКТ"}
PRIMARY_COLOR = {
    "str": (255, 150, 110),
    "agi": (140, 235, 150),
    "int": (130, 190, 255),
}
TEAM_LABEL = {"A": "СВЕТ", "B": "ТЬМА"}
TEAM_COLOR = {"A": (120, 180, 255), "B": (255, 130, 120)}


class MenuUI:
    def __init__(self, game):
        self.portraits = {}
        self._portrait_cache = {}
        self.hero_rects = {}
        self.buttons = {}
        self.setting_rows = {}
        self.ip_rect = None
        self.title_font = pygame.font.SysFont("consolas", 64, bold=True)
        self.card_title = pygame.font.SysFont("consolas", 16, bold=True)
        self.small = pygame.font.SysFont("consolas", 12)
        self.mid = pygame.font.SysFont("consolas", 14)

        self.load_portraits(game)

    def load_portraits(self, game):
        self.portraits.clear()
        self._portrait_cache.clear()
        base = Path(__file__).parent
        for hero_id, hero in game.heroes.items():
            image = gfx.load_sprite(base / hero.get("portrait", ""))
            if image is not None:
                self.portraits[hero_id] = image

    # ---------- helpers ----------
    def _text(self, surface, text, font, color, pos, center=False):
        surf = font.render(str(text), True, color)
        rect = surf.get_rect()
        if center:
            rect.center = pos
        else:
            rect.topleft = pos
        surface.blit(surf, rect)
        return rect

    def _panel(self, surface, rect, accent=(70, 90, 120), fill=(14, 20, 30)):
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, accent, rect, 2, border_radius=10)

    def _button(self, surface, rect, label, action, color=(52, 78, 112)):
        mouse = pygame.mouse.get_pos()
        draw_color = tuple(min(255, c + 22) for c in color) if rect.collidepoint(mouse) else color
        pygame.draw.rect(surface, draw_color, rect, border_radius=8)
        pygame.draw.rect(surface, (130, 155, 190), rect, 2, border_radius=8)
        self._text(surface, label, self.mid, (240, 242, 248), rect.center, center=True)
        self.buttons[action] = rect

    def _scaled_portrait(self, hero_id, size):
        key = (hero_id, size)
        cached = self._portrait_cache.get(key)
        if cached is not None:
            return cached
        image = self.portraits.get(hero_id)
        if image is None:
            return None
        width, height = image.get_size()
        scale = min(size[0] / max(1, width), size[1] / max(1, height))
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        scaled = pygame.transform.smoothscale(image, new_size)
        self._portrait_cache[key] = scaled
        return scaled

    def _portrait(self, surface, hero_id, rect):
        image = self._scaled_portrait(hero_id, (rect.w, rect.h))
        if image is not None:
            surface.blit(image, image.get_rect(center=rect.center))
            return
        hero = self.game_heroes.get(hero_id, {}) if hasattr(self, "game_heroes") else {}
        color = tuple(hero.get("color", (180, 180, 180)))
        pygame.draw.circle(surface, color, rect.center, min(rect.w, rect.h) // 2 - 4)
        name = str(hero.get("name", "?"))
        self._text(surface, name[:1].upper(), self.title_font, (20, 24, 30), rect.center, center=True)

    def _background(self, surface):
        width, height = surface.get_size()
        for y in range(height):
            t = y / max(1, height - 1)
            color = (int(8 + 14 * t), int(18 + 22 * t), int(30 + 20 * t))
            pygame.draw.line(surface, color, (0, y), (width, y))

        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.polygon(
            overlay, (30, 95, 140, 55),
            [(0, 0), (170, 0), (width, height), (width - 170, height)],
        )
        pygame.draw.polygon(
            overlay, (80, 160, 210, 40),
            [(0, 0), (60, 0), (width, height), (width - 60, height)],
        )
        for x in range(0, width, 64):
            pygame.draw.line(overlay, (90, 120, 150, 18), (x, 0), (x, height), 1)
        for y in range(0, height, 64):
            pygame.draw.line(overlay, (90, 120, 150, 18), (0, y), (width, y), 1)
        surface.blit(overlay, (0, 0))

    def _hero_stats(self, game, hero_id):
        hero = game.heroes.get(hero_id, {})
        base = hero.get("base", {})
        prog = game.progression
        primary = hero.get("primary", "str")
        primary_value = base.get(primary, 0)
        hp = base.get("hp", 0) + base.get("str", 0) * prog.get("hp_per_str", 12)
        mana = base.get("mana", 0) + base.get("int", 0) * prog.get("mana_per_int", 8)
        damage = base.get("damage", 0) + primary_value * prog.get("damage_per_primary", 0.8)
        armor = base.get("armor", 0) + base.get("agi", 0) * prog.get("armor_per_agi", 0.15)
        return {
            "hp": hp, "mana": mana, "damage": damage, "armor": armor,
            "speed": base.get("speed", 0), "range": base.get("atk_range", 0),
        }

    # ---------- menu ----------
    def draw_menu(self, surface, game):
        self.game_heroes = game.heroes
        self.hero_rects.clear()
        self.buttons.clear()
        width, height = surface.get_size()
        self._background(surface)

        self._text(surface, "ISOTA", self.title_font, (235, 240, 250), (40, 26))
        self._text(surface, "2D MOBA prototype", self.mid, (140, 170, 200), (44, 95))
        self._text(
            surface, "Выбери героя, затем оффлайн или LAN-лобби",
            self.small, (160, 170, 185), (44, 116),
        )
        self._button(
            surface, pygame.Rect(width - 210, 30, 170, 40),
            "Настройки", "settings", color=(58, 70, 96),
        )

        per_page = 5
        page_count = max(1, (len(game.hero_order) + per_page - 1) // per_page)
        game.hero_page = max(0, min(game.hero_page, page_count - 1))
        visible_heroes = game.hero_order[
            game.hero_page * per_page:(game.hero_page + 1) * per_page
        ]
        card_w, card_h, gap = 180, 190, 16
        total_w = len(visible_heroes) * card_w + (len(visible_heroes) - 1) * gap
        start_x = (width - total_w) // 2
        y = 142

        for index, hero_id in enumerate(visible_heroes):
            hero = game.heroes[hero_id]
            rect = pygame.Rect(start_x + index * (card_w + gap), y, card_w, card_h)
            self.hero_rects[hero_id] = rect
            selected = hero_id == game.selected_hero
            accent = (255, 215, 110) if selected else (65, 85, 110)
            self._panel(surface, rect, accent=accent)

            portrait_rect = pygame.Rect(rect.x + 16, rect.y + 12, rect.w - 32, 112)
            self._portrait(surface, hero_id, portrait_rect)

            primary = hero.get("primary", "str")
            self._text(surface, hero.get("name", hero_id), self.card_title, (235, 238, 245),
                       (rect.centerx, rect.y + 136), center=True)
            self._text(surface, hero.get("title", ""), self.small, (160, 170, 185),
                       (rect.centerx, rect.y + 154), center=True)
            color = PRIMARY_COLOR.get(primary, (220, 220, 220))
            self._text(surface, PRIMARY_LABEL.get(primary, primary).upper(), self.small, color,
                       (rect.centerx, rect.y + 172), center=True)

        if page_count > 1:
            self._button(
                surface, pygame.Rect(start_x - 64, y + 68, 46, 50),
                "<", "hero_prev", color=(45, 60, 85),
            )
            self._button(
                surface, pygame.Rect(start_x + total_w + 18, y + 68, 46, 50),
                ">", "hero_next", color=(45, 60, 85),
            )
            self._text(
                surface, f"{game.hero_page + 1}/{page_count}", self.small,
                (170, 185, 205), (start_x + total_w // 2, y - 10), center=True,
            )

        details = pygame.Rect(100, 350, width - 200, 240)
        self._panel(surface, details, accent=(80, 105, 140), fill=(11, 17, 26))
        self._draw_hero_details(surface, game, details)

        # Buttons.
        button_y = 610
        button_h = 48
        self._button(surface, pygame.Rect(100, button_y, 260, button_h),
                     "Играть оффлайн", "offline", color=(45, 105, 75))
        self._button(surface, pygame.Rect(380, button_y, 300, button_h),
                     "Создать LAN-лобби", "host", color=(55, 80, 130))

        ip_rect = pygame.Rect(700, button_y, 250, button_h)
        self.ip_rect = ip_rect
        focus = game.menu_ip_focus and not game.disconnected
        pygame.draw.rect(surface, (18, 30, 44) if not focus else (25, 48, 68), ip_rect, border_radius=8)
        pygame.draw.rect(surface, (255, 215, 110) if focus else (100, 125, 160), ip_rect, 2, border_radius=8)
        ip_text = game.menu_ip or "IP или IP:порт"
        self._text(surface, ip_text, self.mid, (230, 235, 245), (ip_rect.x + 12, ip_rect.y + 14))
        if focus and (pygame.time.get_ticks() // 500) % 2 == 0:
            tw = self.mid.size(ip_text)[0]
            pygame.draw.line(surface, (255, 255, 255),
                             (ip_rect.x + 12 + tw + 2, ip_rect.y + 12),
                             (ip_rect.x + 12 + tw + 2, ip_rect.y + 36), 2)
        self._button(surface, pygame.Rect(960, button_y, 220, button_h),
                     "Подключиться", "join", color=(90, 70, 120))

        if game.menu_message:
            self._text(surface, game.menu_message, self.mid, (255, 220, 150), (44, 682))
        self._text(
            surface,
            "ПКМ — идти/атаковать · Q/W/E/R — способности · B — магазин · "
            "ПКМ по своему крипу <40% — deny · ~ — консоль",
            self.small, (130, 145, 165), (44, 700),
        )

    def _draw_hero_details(self, surface, game, rect):
        hero_id = game.selected_hero
        hero = game.heroes.get(hero_id, {})
        if not hero:
            return
        primary = hero.get("primary", "str")
        stats = self._hero_stats(game, hero_id)
        base = hero.get("base", {})

        self._text(surface, hero.get("name", hero_id), game.ui.big_font, (245, 245, 250),
                   (rect.x + 24, rect.y + 16))
        self._text(surface, hero.get("title", ""), self.mid, (165, 180, 200),
                   (rect.x + 24, rect.y + 42))
        color = PRIMARY_COLOR.get(primary, (220, 220, 220))
        self._text(surface, f"Основной атрибут: {PRIMARY_LABEL.get(primary, primary)}",
                   self.mid, color, (rect.x + 24, rect.y + 66))
        attack_type = "Ближний бой" if hero.get("melee") else "Дальний бой"
        self._text(surface, attack_type, self.mid, (210, 220, 235),
                   (rect.x + 310, rect.y + 66))

        attrs = [
            ("СИЛА", int(base.get("str", 0)), PRIMARY_COLOR["str"]),
            ("ЛОВКОСТЬ", int(base.get("agi", 0)), PRIMARY_COLOR["agi"]),
            ("ИНТЕЛЛЕКТ", int(base.get("int", 0)), PRIMARY_COLOR["int"]),
        ]
        for i, (label, value, col) in enumerate(attrs):
            x = rect.x + 24 + i * 130
            pygame.draw.circle(surface, col, (x + 6, rect.y + 108), 5)
            self._text(surface, f"{label} {value}", self.mid, (220, 225, 235),
                       (x + 18, rect.y + 100))

        stat_pairs = [
            ("HP", int(stats["hp"])), ("Мана", int(stats["mana"])),
            ("Урон", int(stats["damage"])), ("Броня", f"{stats['armor']:.1f}"),
            ("Скорость", f"{stats['speed']:.2f}"), ("Дальность", f"{stats['range']:.1f}"),
        ]
        for i, (label, value) in enumerate(stat_pairs):
            col = i % 3
            row = i // 3
            x = rect.x + 24 + col * 155
            y = rect.y + 132 + row * 24
            self._text(surface, f"{label}: {value}", self.mid, (200, 210, 225), (x, y))

        passive = hero.get("passive") or {}
        if passive:
            passive_text = game.ui._fit_text(
                f"ПАССИВ · {passive.get('name', '')}: {passive.get('desc', '')}",
                self.small, 500,
            )
            self._text(surface, passive_text, self.small, (210, 165, 255),
                       (rect.x + 24, rect.y + 186))

        ab_x = rect.x + 540
        self._text(surface, "СПОСОБНОСТИ", self.mid, (255, 220, 130), (ab_x, rect.y + 16))
        abilities = hero.get("abilities", [])
        for i, ability in enumerate(abilities[:4]):
            y = rect.y + 44 + i * 44
            key = ability.get("key", "?")
            badge = pygame.Rect(ab_x, y, 28, 28)
            pygame.draw.rect(surface, (45, 65, 90), badge, border_radius=5)
            pygame.draw.rect(surface, (150, 180, 220), badge, 1, border_radius=5)
            self._text(surface, key, self.mid, (245, 245, 250), badge.center, center=True)
            self._text(surface, ability.get("name", ""), self.mid, (235, 238, 245),
                       (ab_x + 38, y + 1))
            self._text(surface, ability.get("desc", ""), self.small, (165, 178, 195),
                       (ab_x + 38, y + 17))
            self._text(
                surface,
                f"{ability.get('mana', 0)} маны   КД {ability.get('cooldown', 0):.0f}с",
                self.small, (150, 165, 185),
                (ab_x + 330, y + 6),
            )

    # ---------- lobby ----------
    def draw_lobby(self, surface, game):
        self.game_heroes = game.heroes
        self.hero_rects.clear()
        self.buttons.clear()
        width, height = surface.get_size()
        self._background(surface)

        self._text(surface, "ЛОББИ", self.title_font, (235, 240, 250), (40, 26))
        self._text(surface, f"IP: {game.lobby_ip()}", game.ui.big_font, (150, 225, 255),
                   (44, 96))
        self._text(surface, "Передай этот адрес второму игроку. Порт указывается через двоеточие.",
                   self.small, (160, 175, 195), (44, 124))

        players = game.lobby.get("players", []) if isinstance(game.lobby, dict) else []
        max_players = int(game.lobby.get("max_players", game.max_players) or game.max_players)
        waiting = max(0, max_players - len(players))
        if waiting > 0:
            status = f"Ожидание игроков: {len(players)}/{max_players}"
            status_color = (255, 220, 140)
        else:
            status = "Все игроки подключились"
            status_color = (150, 235, 160)
        self._text(surface, status, self.mid, status_color, (44, 142))

        panel = pygame.Rect(100, 176, 540, 350)
        self._panel(surface, panel, accent=(80, 105, 140), fill=(11, 17, 26))
        self._text(surface, "ИГРОКИ", self.mid, (255, 220, 130), (panel.x + 18, panel.y + 14))

        if not players:
            self._text(surface, "Ожидание подключения...", self.mid, (170, 180, 195),
                       (panel.x + 18, panel.y + 52))
        for i, player in enumerate(players[: max_players]):
            y = panel.y + 50 + i * 56
            row = pygame.Rect(panel.x + 14, y, panel.w - 28, 48)
            pygame.draw.rect(surface, (18, 27, 39), row, border_radius=6)
            pygame.draw.rect(surface, (55, 75, 100), row, 1, border_radius=6)
            team = player.get("team", "A")
            team_color = TEAM_COLOR.get(team, (220, 220, 220))
            pygame.draw.circle(surface, team_color, (row.x + 18, row.y + 24), 8)
            name = str(player.get("name", "?"))
            if player.get("id") == game.player_id:
                name += " (ты)"
            if player.get("host"):
                name += " [хост]"
            self._text(surface, name, self.mid, (235, 238, 245), (row.x + 36, row.y + 7))
            hero_id = player.get("hero")
            hero_name = game.heroes.get(hero_id, {}).get("name", "герой не выбран")
            self._text(surface, hero_name, self.small, (165, 180, 200), (row.x + 36, row.y + 26))
            ready = "ГОТОВ" if player.get("ready") else "не готов"
            ready_color = (140, 230, 150) if player.get("ready") else (200, 170, 120)
            self._text(surface, ready, self.small, ready_color, (row.right - 70, row.y + 16))

        picker = pygame.Rect(700, 176, width - 800, 350)
        self._panel(surface, picker, accent=(80, 105, 140), fill=(11, 17, 26))
        self._text(surface, "ТВОЙ ГЕРОЙ", self.mid, (255, 220, 130), (picker.x + 18, picker.y + 14))

        my_hero = next(
            (p.get("hero") for p in players if p.get("id") == game.player_id), None
        )
        cell_w = (picker.w - 42) // 2
        for i, hero_id in enumerate(game.hero_order):
            hero = game.heroes[hero_id]
            col = i % 2
            row_index = i // 2
            row = pygame.Rect(
                picker.x + 14 + col * (cell_w + 14),
                picker.y + 44 + row_index * 56,
                cell_w,
                48,
            )
            self.hero_rects[hero_id] = row
            selected = hero_id == game.selected_hero
            pygame.draw.rect(surface, (24, 38, 52) if selected else (18, 27, 39), row,
                             border_radius=6)
            pygame.draw.rect(surface, (255, 215, 110) if selected else (55, 75, 100),
                             row, 2 if selected else 1, border_radius=6)
            portrait_rect = pygame.Rect(row.x + 5, row.y + 5, 38, 38)
            self._portrait(surface, hero_id, portrait_rect)
            name = game.ui._fit_text(hero.get("name", hero_id), self.mid, cell_w - 92)
            self._text(surface, name, self.mid, (235, 238, 245), (row.x + 50, row.y + 5))
            primary = hero.get("primary", "str")
            self._text(surface, PRIMARY_LABEL.get(primary, primary), self.small,
                       PRIMARY_COLOR.get(primary, (200, 200, 200)), (row.x + 50, row.y + 25))
            if my_hero == hero_id:
                pygame.draw.circle(surface, (255, 215, 110), (row.right - 12, row.y + 12), 4)

        button_y = 570
        me = next((p for p in players if p.get("id") == game.player_id), None)
        is_ready = bool(me and me.get("ready"))
        ready_label = "Отменить готовность" if is_ready else "Я готов"
        self._button(
            surface, pygame.Rect(100, button_y, 280, 48), ready_label, "ready",
            color=(45, 105, 75) if is_ready else (55, 80, 130),
        )
        if game.is_host:
            all_ready = bool(players) and all(p.get("ready") for p in players)
            self._button(
                surface, pygame.Rect(400, button_y, 260, 48), "Начать игру", "start",
                color=(100, 80, 45) if not all_ready else (55, 95, 145),
            )
        self._button(surface, pygame.Rect(680, button_y, 200, 48), "Выйти", "leave",
                     color=(100, 55, 55))

        if game.disconnected:
            self._text(surface, "СОЕДИНЕНИЕ ПОТЕРЯНО", game.ui.big_font, (255, 120, 120),
                       (44, 650))
        elif game.menu_message:
            self._text(surface, game.menu_message, self.mid, (255, 220, 150), (44, 650))
        self._text(surface, "Готовность → Start у хоста. Enter — переключить готовность.",
                   self.small, (130, 145, 165), (44, 690))

    # ---------- input ----------
    def draw_settings(self, surface, game):
        self.buttons.clear()
        self.setting_rows.clear()
        width, height = surface.get_size()
        self._background(surface)
        self._text(surface, "НАСТРОЙКИ", self.title_font, (235, 240, 250), (40, 26))
        self._text(surface, "Управление", game.ui.big_font, (150, 225, 255), (44, 96))
        self._text(
            surface, "Нажми на действие, затем нажми новую клавишу.",
            self.small, (160, 175, 195), (44, 124),
        )

        panel = pygame.Rect(220, 158, width - 440, 360)
        self._panel(surface, panel, accent=(80, 105, 140), fill=(11, 17, 26))

        actions = [
            ("stop", "Остановка"),
            ("ability_1", "Способность 1"),
            ("ability_2", "Способность 2"),
            ("ability_3", "Способность 3"),
            ("ability_4", "Способность 4"),
            ("shop", "Магазин"),
        ]
        for i, (action, label) in enumerate(actions):
            row = pygame.Rect(panel.x + 24, panel.y + 28 + i * 56, panel.w - 48, 44)
            self.setting_rows[action] = row
            active = game.settings_action == action
            pygame.draw.rect(surface, (32, 48, 66) if active else (18, 27, 39),
                             row, border_radius=7)
            pygame.draw.rect(surface, (255, 215, 110) if active else (55, 75, 100),
                             row, 2 if active else 1, border_radius=7)
            self._text(surface, label, self.mid, (230, 235, 245), (row.x + 14, row.y + 12))
            code = game.control_codes.get(action, 0)
            key_name = pygame.key.name(code).upper() if code else "—"
            if active:
                key_name = "нажми клавишу..."
            self._text(surface, key_name, self.mid, (150, 220, 255),
                       (row.right - 180, row.y + 12))

        note = self.small.render(
            "ПКМ — атака, стрелки — камера (фиксировано). Esc / ~ / F1 зарезервированы.",
            True, (135, 150, 170),
        )
        surface.blit(note, (panel.x + 24, panel.bottom + 18))

        self._button(surface, pygame.Rect(220, 560, 220, 46), "Сброс", "reset",
                     color=(90, 70, 70))
        self._button(surface, pygame.Rect(460, 560, 220, 46), "Назад", "back",
                     color=(55, 80, 130))

        if game.settings_message:
            self._text(surface, game.settings_message, self.mid, (255, 220, 150),
                       (44, 660))

    def handle_click(self, pos, game):
        if game.state == "settings":
            for action, rect in self.setting_rows.items():
                if rect.collidepoint(pos):
                    game.settings_action = action
                    game.settings_message = ""
                    return
            if "reset" in self.buttons and self.buttons["reset"].collidepoint(pos):
                game.reset_controls()
            elif "back" in self.buttons and self.buttons["back"].collidepoint(pos):
                game.state = "menu"
                game.settings_action = None
            return

        if game.state == "menu":
            if "hero_prev" in self.buttons and self.buttons["hero_prev"].collidepoint(pos):
                game.hero_page = max(0, game.hero_page - 1)
                return
            if "hero_next" in self.buttons and self.buttons["hero_next"].collidepoint(pos):
                game.hero_page += 1
                return

            for hero_id, rect in self.hero_rects.items():
                if rect.collidepoint(pos):
                    game.selected_hero = hero_id
                    game.hero_id = hero_id
                    game._setup_abilities()
                    game.menu_ip_focus = False
                    return

            if self.ip_rect and self.ip_rect.collidepoint(pos):
                game.menu_ip_focus = True
                return
            game.menu_ip_focus = False

            if "offline" in self.buttons and self.buttons["offline"].collidepoint(pos):
                game.start_offline_game(game.selected_hero)
            elif "host" in self.buttons and self.buttons["host"].collidepoint(pos):
                game.start_host_lobby()
            elif "join" in self.buttons and self.buttons["join"].collidepoint(pos):
                self._join(game)
            elif "settings" in self.buttons and self.buttons["settings"].collidepoint(pos):
                game.state = "settings"
                game.settings_action = None
                game.settings_message = ""
            return

        if game.state == "lobby":
            for hero_id, rect in self.hero_rects.items():
                if rect.collidepoint(pos):
                    game.selected_hero = hero_id
                    game.hero_id = hero_id
                    game._setup_abilities()
                    if game.net and not game.disconnected:
                        try:
                            game.net.send({"type": "select_hero", "hero": hero_id})
                        except (ConnectionError, OSError):
                            game.disconnected = True
                    return

            if "ready" in self.buttons and self.buttons["ready"].collidepoint(pos):
                game.toggle_ready()
            elif "start" in self.buttons and self.buttons["start"].collidepoint(pos):
                game.start_match()
            elif "leave" in self.buttons and self.buttons["leave"].collidepoint(pos):
                game.leave_lobby()

    def _join(self, game):
        value = (game.menu_ip or "").strip()
        if not value:
            game.menu_message = "Введи IP хоста"
            return
        port = game.port
        host = value
        if ":" in value:
            host, port_text = value.rsplit(":", 1)
            try:
                port = int(port_text)
            except ValueError:
                game.menu_message = "Неверный порт"
                return
        game.menu_ip_focus = False
        game.join_lobby(host, port)

    def handle_key(self, event, game):
        if game.state == "settings":
            if game.settings_action:
                key_name = pygame.key.name(event.key)
                if game.set_control(game.settings_action, key_name):
                    game.settings_action = None
            return

        if game.state == "menu" and game.menu_ip_focus:
            if event.key == pygame.K_BACKSPACE:
                game.menu_ip = game.menu_ip[:-1]
            elif event.key == pygame.K_RETURN:
                self._join(game)
            elif event.key == pygame.K_ESCAPE:
                game.menu_ip_focus = False
            elif event.unicode and event.unicode.isprintable() and len(game.menu_ip) < 64:
                game.menu_ip += event.unicode
            return

        if game.state == "lobby" and event.key == pygame.K_RETURN:
            game.toggle_ready()
