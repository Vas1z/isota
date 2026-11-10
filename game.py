import json
import math
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pygame

import gfx
import loader
from console import Console
from menu import MenuUI
from netclient import NetClient
from shared.netutil import lan_ip
from shared.protocol import DEFAULT_PORT
from shared.sim import Unit, World
from ui import FloatingText, UI


# ---------- Топ-даун координаты ----------
class Grid:
    tile_size = 48
    grid_w = 24
    grid_h = 24
    zoom = 1.0

    @classmethod
    def to_screen(cls, gx, gy):
        sx = gx * cls.tile_size * cls.zoom
        sy = gy * cls.tile_size * cls.zoom
        return sx, sy

    @classmethod
    def to_grid(cls, sx, sy):
        gx = sx / (cls.tile_size * cls.zoom)
        gy = sy / (cls.tile_size * cls.zoom)
        return gx, gy


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class ProjectileView:
    pos: Tuple[float, float]
    color: Tuple[int, int, int] = (255, 240, 150)
    radius: int = 4


@dataclass
class Snapshot:
    t: float
    data: dict


@dataclass
class AbilityEffect:
    x: float
    y: float
    radius: float
    color: Tuple[int, int, int]
    lifetime: float = 0.6
    max_lifetime: float = 0.6

    def update(self, dt: float) -> None:
        self.lifetime -= dt


@dataclass
class MeleeEffect:
    x: float
    y: float
    angle: float
    color: Tuple[int, int, int]
    lifetime: float = 0.18
    max_lifetime: float = 0.18

    def update(self, dt: float) -> None:
        self.lifetime -= dt


# Насколько клиент отстаёт от последнего снапшота. Даёт буфер для интерполяции.
INTERP_DELAY = 0.06

DEFAULT_CONTROLS = {
    "stop": "s",
    "ability_1": "q",
    "ability_2": "w",
    "ability_3": "e",
    "ability_4": "r",
    "shop": "b",
}

KEY_CODES = {}
for _code in range(32, 512):
    _name = pygame.key.name(_code)
    if _name:
        KEY_CODES[_name] = _code


# ---------- Камера ----------
class Camera:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.scroll_speed = 600.0

    def move(self, dx: float, dy: float):
        self.x += dx
        self.y += dy

    def clamp_to_world(self, view_w: int, view_h: int):
        world_w = Grid.grid_w * Grid.tile_size * Grid.zoom
        world_h = Grid.grid_h * Grid.tile_size * Grid.zoom

        if world_w <= view_w:
            self.x = -(view_w - world_w) / 2
        else:
            self.x = max(0, min(self.x, world_w - view_w))

        if world_h <= view_h:
            self.y = -(view_h - world_h) / 2
        else:
            self.y = max(0, min(self.y, world_h - view_h))

    def apply(self, wx: float, wy: float) -> Tuple[float, float]:
        return wx - self.x, wy - self.y


# ---------- Игра (клиент) ----------
class Game:
    def __init__(self, mode: str = "offline", host: Optional[str] = None,
                 port: int = DEFAULT_PORT, name: str = "Player"):
        self.data = loader.load_all()
        loader.validate(self.data)

        self.Grid = Grid
        self.heroes_data = self.data["heroes"]
        self.progression = self.heroes_data.get("progression", {})
        self.heroes = self.heroes_data["heroes"]
        self.hero_order = list(self.heroes.keys())
        self.items_data = self.data["items"]["items"]
        self.max_level = int(self.progression.get("max_level", 10))
        self.selected_hero = self.hero_order[0]
        self.hero_id = self.selected_hero
        self.hero_page = 0

        self.cfg = self.data["settings"]
        self.controls = self.data["controls"]
        for action, key_name in DEFAULT_CONTROLS.items():
            self.controls.setdefault(action, key_name)
        self.control_codes = {
            action: KEY_CODES.get(self.controls.get(action, key_name), 0)
            for action, key_name in DEFAULT_CONTROLS.items()
        }
        self.settings_action: Optional[str] = None
        self.settings_message = ""
        self.map_cfg = self.data["map"]
        self.colors = {k: tuple(v) for k, v in self.cfg["colors"].items()}

        debug_cfg = self.cfg.get("debug", {})
        self.show_grid = debug_cfg.get("show_grid", False)
        self.show_hitboxes = debug_cfg.get("show_hitboxes", False)
        self.show_fps = debug_cfg.get("show_fps", False)
        self.grid_color = tuple(debug_cfg.get("grid_color", [255, 255, 255, 80]))
        self.text_color = tuple(debug_cfg.get("text_color", [255, 255, 0]))

        Grid.tile_size = 48
        Grid.zoom = self.cfg["iso"].get("zoom", 1.0)
        Grid.grid_w = self.cfg["grid"]["width"]
        Grid.grid_h = self.cfg["grid"]["height"]

        self.lanes = {k: [tuple(p) for p in v] for k, v in self.map_cfg["lanes"].items()}
        self.bases = {k: tuple(v) for k, v in self.map_cfg["bases"].items()}
        self.spawns = {
            k: tuple(v)
            for k, v in self.map_cfg.get("spawns", {"A": [4, 20], "B": [20, 4]}).items()
        }

        self.net_mode = mode == "net"
        self.state = "lobby" if self.net_mode else "menu"
        self.player_name = name
        self.port = port
        self.max_players = 1
        self.online_players = 0
        self.player_id: Optional[str] = None
        self.team = "A"
        self.hero_uid: Optional[int] = None
        self.net: Optional[NetClient] = None
        self.disconnected = False
        self.status_message = ""
        self.ping_ms = 0
        self.server_addr = ""
        self.lan_ip = ""
        self.lobby: dict = {}
        self.host_id: Optional[str] = None
        self.is_host = False
        self.menu_message = ""
        self.menu_ip = host or "127.0.0.1"
        self.menu_ip_focus = False
        self.local_server_thread = None
        self.local_server_port = None
        self.quit_requested = False
        self._manual_ping = False
        self._ping_timer = 0.0
        self._seq = 0
        self.snaps: deque = deque(maxlen=40)

        self.world: Optional[World] = None
        self.units: List[Unit] = []
        self.projectiles: List[ProjectileView] = []
        self.floating_texts: List[FloatingText] = []
        self.hero: Optional[Unit] = None

        self.match_time = 0.0
        self.gold = 0
        self.cs = 0
        self.denies = 0
        self.kills = 0
        self.deaths = 0
        self.assists = 0
        self.level = 1
        self.xp = 0.0
        self.xp_next = 100.0
        self.mana = 0.0
        self.max_mana = 0.0
        self.str = 0.0
        self.agi = 0.0
        self.int = 0.0
        self.items: List[str] = []
        self.cooldowns: dict = {}
        self.abilities: list = []
        self.pending_ability: Optional[int] = None
        self.shop_open = False
        self.shop_message = ""
        self.scoreboard_open = False
        self.ability_effects: list = []
        self.melee_effects: list = []
        self.respawn_timer = 0.0
        self.match_over = False
        self.winner: Optional[str] = None

        self.move_marker: Optional[Tuple[float, float]] = None
        self.attack_marker_uid: Optional[int] = None

        # --- подключение до создания окна ---
        if self.net_mode:
            self._connect(host or "127.0.0.1", port, name)
            self.state = "lobby"
            try:
                self.net.send({"type": "select_hero", "hero": self.selected_hero})
            except (ConnectionError, OSError):
                self.disconnected = True
        else:
            self.state = "menu"

        # --- pygame ---
        pygame.init()
        self.windowed_w = self.cfg["screen"]["width"]
        self.windowed_h = self.cfg["screen"]["height"]
        self.is_fullscreen = False

        self.screen = pygame.display.set_mode((self.windowed_w, self.windowed_h))
        caption = "MOBA Prototype — LAN" if self.net_mode else "MOBA Prototype — Offline"
        pygame.display.set_caption(caption)

        self.clock = pygame.time.Clock()
        self.fps = self.cfg["screen"]["fps"]

        self.camera = Camera()
        cam_cfg = self.cfg["camera"]
        self.camera.scroll_speed = cam_cfg.get("scroll_speed", 600.0)

        self._mmb_down = False
        self._mmb_last = (0, 0)
        self.show_ui = True

        self.ui = UI(self)
        self.creep_sprites = {}
        self._sprite_cache = {}
        self.sprite_errors = []
        self._load_creep_sprites()
        self.item_icons = {}
        near = Path(__file__).parent
        for item_id, item in self.items_data.items():
            icon_name = item.get("icon")
            if icon_name:
                image = gfx.load_sprite(near / icon_name)
                if image is not None:
                    self.item_icons[item_id] = image

        self.neutral_sprites = {}
        self._neutral_sprite_cache = {}
        for neutral_id in self.data.get("neutrals", {}):
            image = gfx.load_sprite(near / "assets" / "neutrals" / f"{neutral_id}.png")
            if image is not None:
                self.neutral_sprites[neutral_id] = image

        self.console = Console(self)
        self.menu = MenuUI(self)
        if self.state == "game":
            self._center_camera_on_team_spawn()

        for name, error in self.sprite_errors:
            self.console.log(f"sprite {name}: {error}", (255, 180, 120))

        if self.net_mode:
            self.console.log(
                f"connected to {self.server_addr} as {self.player_id} ({self.team})",
                (120, 220, 150),
            )
        else:
            self.console.log("offline mode", (150, 150, 150))
        self.console.log("press ~ or F1 to open this console", (150, 150, 150))

    # ---------- настройки управления ----------
    def save_controls(self) -> None:
        path = Path(__file__).parent / "data" / "controls.json"
        try:
            with path.open("w", encoding="utf-8") as file:
                json.dump(self.controls, file, ensure_ascii=False, indent=2)
                file.write("\n")
        except OSError as exc:
            self.settings_message = f"Не удалось сохранить: {exc}"

    def set_control(self, action: str, key_name: str) -> bool:
        if action not in DEFAULT_CONTROLS:
            return False
        if key_name in ("", "unknown", "escape", "backquote", "f1"):
            self.settings_message = "Эта клавиша зарезервирована"
            return False
        code = KEY_CODES.get(key_name)
        if not code:
            self.settings_message = "Неизвестная клавиша"
            return False
        for other_action, other_code in self.control_codes.items():
            if other_action != action and other_code == code:
                self.settings_message = (
                    f"Клавиша уже используется: {pygame.key.name(other_code).upper()}"
                )
                return False
        self.controls[action] = key_name
        self.control_codes[action] = code
        self.settings_message = f"Назначено: {key_name.upper()}"
        self.save_controls()
        return True

    def reset_controls(self) -> None:
        for action, key_name in DEFAULT_CONTROLS.items():
            self.controls[action] = key_name
            self.control_codes[action] = KEY_CODES.get(key_name, 0)
        self.settings_message = "Управление сброшено"
        self.save_controls()

    # ---------- режимы ----------
    def _setup_abilities(self) -> None:
        hero_cfg = self.heroes.get(self.hero_id, {})
        self.abilities = list(hero_cfg.get("abilities", []))

    def start_offline_game(self, hero_id: Optional[str] = None) -> None:
        if hero_id not in self.heroes:
            hero_id = self.hero_order[0]
        self.selected_hero = hero_id
        self.hero_id = hero_id
        self.net_mode = False
        self.state = "game"
        self.world = World(self.data)
        self.world.add_player("local", "A", self.player_name, hero_id)
        self.player_id = "local"
        self.team = "A"
        self.max_players = 1
        self.online_players = 1
        self.hero = self.world.players["local"].hero
        self.hero_uid = self.hero.uid
        self.units = self.world.units
        self.projectiles = []
        self.snaps.clear()
        self.match_over = False
        self.winner = None
        self.shop_open = False
        self.shop_message = ""
        self.scoreboard_open = False
        self.pending_ability = None
        self.move_marker = None
        self.attack_marker_uid = None
        self.floating_texts = []
        self.ability_effects = []
        self.melee_effects = []
        self.disconnected = False
        self.status_message = ""
        self.menu_message = ""
        self._sync_offline_player()
        self._setup_abilities()
        self._center_camera_on_team_spawn()
        self.console.log(
            f"offline game started: {self.heroes[hero_id]['name']}",
            (150, 220, 150),
        )

    def _connect(self, host: str, port: int, name: str) -> None:
        last_error = None

        # Если сервер только поднимается (или хост перезапустил игру),
        # несколько быстрых попыток заметно снижают шанс поймать отказ.
        for attempt in range(3):
            try:
                self.net = NetClient(host, port, name, connect_timeout=3.0)
                last_error = None
                break
            except ConnectionRefusedError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.7)
            except OSError as exc:
                last_error = exc
                break

        if self.net is None:
            raise RuntimeError(
                f"не удалось подключиться к {host}:{port}: {last_error}"
            ) from last_error

        deadline = time.monotonic() + 5.0

        while time.monotonic() < deadline:
            for msg in self.net.poll():
                mtype = msg.get("type")
                if mtype == "welcome":
                    self.player_id = msg.get("player_id")
                    self.team = msg.get("team", "A")
                    self.max_players = int(msg.get("max_players", 2))
                    self.host_id = msg.get("host")
                    self.is_host = self.host_id == self.player_id
                    self.server_addr = f"{host}:{port}"
                    self.lan_ip = lan_ip()
                    self.status_message = f"Онлайн: {host}:{port}"
                    return
                if mtype == "error":
                    message = msg.get("message", "server error")
                    self.net.close()
                    raise RuntimeError(f"сервер {host}:{port}: {message}")
                if mtype == "_disconnected":
                    raise RuntimeError(f"сервер {host}:{port} закрыл соединение")
            time.sleep(0.01)

        self.net.close()
        raise RuntimeError(
            f"сервер {host}:{port} не прислал welcome "
            "(порт занят другим сервисом?)"
        )

    # ---------- спрайты ----------
    def _load_sprite_image(self, path: Path):
        """Загружает PNG через pygame, а при проблемах с libpng — через Pillow."""
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error as pygame_error:
            try:
                from PIL import Image

                with Image.open(path) as pil_image:
                    pil_image = pil_image.convert("RGBA")
                    size = pil_image.size
                    data = pil_image.tobytes()

                return pygame.image.fromstring(data, size, "RGBA").convert_alpha()
            except Exception as pillow_error:
                self.sprite_errors.append(
                    (path.name, f"pygame: {pygame_error}; Pillow: {pillow_error}")
                )
                return None
        except OSError as exc:
            self.sprite_errors.append((path.name, str(exc)))
            return None

    def _load_creep_sprites(self) -> None:
        assets = Path(__file__).parent / "assets"
        for team, filename in (
            ("A", "creep_melee_a.png"),
            ("B", "creep_melee_b.png"),
        ):
            path = assets / filename
            if not path.exists():
                continue

            image = self._load_sprite_image(path)
            if image is None:
                continue

            # Обрезаем прозрачные поля, чтобы персонаж занимал весь спрайт.
            bounds = image.get_bounding_rect()
            if bounds.w > 0 and bounds.h > 0:
                image = image.subsurface(bounds).copy()

            self.creep_sprites[team] = image

    def reload_sprites(self):
        self.creep_sprites.clear()
        self._sprite_cache.clear()
        self.sprite_errors.clear()
        self._load_creep_sprites()
        for name, error in self.sprite_errors:
            self.console.log(f"sprite {name}: {error}", (255, 180, 120))

        near = Path(__file__).parent
        self.item_icons.clear()
        for item_id, item in self.items_data.items():
            icon_name = item.get("icon")
            if icon_name:
                image = gfx.load_sprite(near / icon_name)
                if image is not None:
                    self.item_icons[item_id] = image

        self.neutral_sprites.clear()
        self._neutral_sprite_cache.clear()
        for neutral_id in self.data.get("neutrals", {}):
            image = gfx.load_sprite(near / "assets" / "neutrals" / f"{neutral_id}.png")
            if image is not None:
                self.neutral_sprites[neutral_id] = image

        if hasattr(self, "menu"):
            self.menu.load_portraits(self)

        return sorted(self.creep_sprites)

    def _get_neutral_sprite(self, neutral_type: str, size: int):
        key = ("neutral", neutral_type, size)
        cached = self._neutral_sprite_cache.get(key)
        if cached is not None:
            return cached
        image = self.neutral_sprites.get(neutral_type)
        if image is None:
            return None
        width, height = image.get_size()
        scale = size / max(width, height)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        scaled = pygame.transform.smoothscale(image, new_size)
        self._neutral_sprite_cache[key] = scaled
        return scaled

    def _get_creep_sprite(self, team: str, size: int):
        key = (team, size)
        cached = self._sprite_cache.get(key)
        if cached is not None:
            return cached

        image = self.creep_sprites.get(team)
        if image is None:
            source = self.creep_sprites.get("A") or self.creep_sprites.get("B")
            if source is None:
                return None
            image = source.copy()
            tint = (255, 140, 140, 255) if team == "B" else (150, 190, 255, 255)
            image.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)

        width, height = image.get_size()
        scale = size / max(width, height)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        scaled = pygame.transform.smoothscale(image, new_size)
        self._sprite_cache[key] = scaled
        return scaled

    # ---------- состояние ----------
    def _sync_offline_player(self) -> None:
        if not self.world or not self.player_id:
            return
        player = self.world.players[self.player_id]
        self.hero = player.hero
        self.hero_uid = player.hero.uid
        self.hero_id = player.hero_id
        self.gold = int(player.gold)
        self.cs = player.cs
        self.denies = player.denies
        self.kills = player.kills
        self.deaths = player.deaths
        self.assists = player.assists
        self.level = player.level
        self.xp = player.xp
        self.xp_next = player.xp_next
        self.str = player.str
        self.agi = player.agi
        self.int = player.int
        self.mana = player.mana
        self.max_mana = player.max_mana
        self.items = list(player.items)
        self.cooldowns = dict(player.cooldowns)
        self.respawn_timer = player.respawn_timer
        self.match_time = self.world.match_time
        self.match_over = self.world.match_over
        self.winner = self.world.winner

    def _sync_offline_world(self) -> None:
        if not self.world:
            return
        self.units = self.world.units
        self.projectiles = [
            ProjectileView(pos=p.pos, color=p.color, radius=p.radius)
            for p in self.world.projectiles
        ]
        self._sync_offline_player()

    def _pump_net(self) -> None:
        if not self.net:
            return

        for msg in self.net.poll():
            mtype = msg.get("type")

            if mtype == "snap":
                data = msg.get("data")
                if isinstance(data, dict):
                    self.snaps.append(Snapshot(time.monotonic(), data))
                for event in msg.get("events", []):
                    self._handle_event(event)

            elif mtype == "lobby":
                self.lobby = msg
                self.host_id = msg.get("host")
                self.is_host = self.host_id == self.player_id
                if self.state != "game":
                    self.state = "lobby"

            elif mtype == "match_start":
                self.state = "game"
                self.match_over = False
                self.winner = None
                self.status_message = ""
                self.snaps.clear()
                self.shop_open = False
                self.shop_message = ""
                self.scoreboard_open = False
                self.pending_ability = None
                self.move_marker = None
                self.attack_marker_uid = None
                self.units = []
                self.projectiles = []
                self.hero = None
                self.hero_uid = None
                self.floating_texts = []
                self.ability_effects = []
                self.melee_effects = []
                self.match_time = 0.0
                info = (msg.get("players") or {}).get(self.player_id, {})
                hero_id = info.get("hero")
                if hero_id in self.heroes:
                    self.hero_id = hero_id
                    self.selected_hero = hero_id
                self._setup_abilities()
                self.console.log("match started", (150, 220, 150))
                self._center_camera_on_team_spawn()

            elif mtype == "pong":
                sent = msg.get("t")
                if isinstance(sent, (int, float)):
                    self.ping_ms = max(0, int((time.monotonic() - sent) * 1000))
                    if self._manual_ping:
                        self._manual_ping = False
                        self.console.log(f"pong: {self.ping_ms} ms", (150, 220, 150))

            elif mtype == "player_left":
                text = f"Игрок {msg.get('name', '?')} отключился"
                self.status_message = text
                self.console.log(text, (255, 200, 120))

            elif mtype == "error":
                text = f"Сервер: {msg.get('message', 'error')}"
                self.status_message = text
                self.menu_message = text
                self.console.log(text, (255, 120, 120))

            elif mtype == "_disconnected":
                self.disconnected = True
                self._manual_ping = False
                self.status_message = "Соединение потеряно"
                self.menu_message = "Соединение потеряно"
                self.console.log("disconnected from server", (255, 120, 120))

    def _handle_event(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "bounty" and event.get("player") == self.player_id:
            sx, sy = Grid.to_screen(event.get("x", 0), event.get("y", 0))
            self.floating_texts.append(FloatingText(
                text=f"+{event.get('amount', 0)}",
                pos=(sx + random.randint(-10, 10), sy - 20),
                color=(255, 215, 0),
                vy=-50,
                vx=random.randint(-20, 20),
            ))
        elif kind == "hero_death" and event.get("player") == self.player_id:
            self.status_message = f"Вы погибли. Респавн через {event.get('respawn', 0):.1f}с"
        elif kind == "respawn" and event.get("player") == self.player_id:
            self.status_message = ""
        elif kind == "level_up" and event.get("player") == self.player_id:
            level = int(event.get("level", 0))
            self.console.log(f"level up! now level {level}", (180, 230, 130))
            if self.hero is not None:
                sx, sy = Grid.to_screen(self.hero.pos[0], self.hero.pos[1])
                self.floating_texts.append(FloatingText(
                    text=f"LEVEL {level}",
                    pos=(sx + random.randint(-15, 15), sy - 45),
                    color=(180, 240, 120),
                    lifetime=1.2,
                    vy=-50,
                ))
        elif kind == "deny" and event.get("player") == self.player_id:
            sx, sy = Grid.to_screen(event.get("x", 0), event.get("y", 0))
            self.floating_texts.append(FloatingText(
                text="DENY!",
                pos=(sx, sy - 25),
                color=(200, 150, 255),
                lifetime=0.9,
                vy=-35,
            ))
            self.console.log("deny! own creep killed", (200, 150, 255))
        elif kind == "purchase" and event.get("player") == self.player_id:
            item = self.items_data.get(event.get("item"), {})
            self.console.log(
                f"purchased: {item.get('name', event.get('item'))}",
                (180, 230, 150),
            )
            self.shop_message = f"Куплено: {item.get('name', event.get('item'))}"
        elif kind == "shop_error" and event.get("player") == self.player_id:
            self.shop_message = str(event.get("message", "Ошибка магазина"))
            self.console.log(f"shop: {self.shop_message}", (255, 160, 100))
        elif kind == "ability":
            color = event.get("color", [255, 255, 255])
            self.ability_effects.append(AbilityEffect(
                x=float(event.get("x", 0)),
                y=float(event.get("y", 0)),
                radius=max(0.6, float(event.get("radius", 0.0))),
                color=tuple(color) if isinstance(color, (list, tuple)) else (255, 255, 255),
                lifetime=0.7,
                max_lifetime=0.7,
            ))
        elif kind == "melee_attack":
            color = event.get("color", [255, 230, 160])
            self.melee_effects.append(MeleeEffect(
                x=float(event.get("x", 0)),
                y=float(event.get("y", 0)),
                angle=float(event.get("angle", 0.0)),
                color=tuple(color) if isinstance(color, (list, tuple)) else (255, 230, 160),
            ))
        elif kind == "match_end":
            self.match_over = True
            winner = event.get("winner")
            self.winner = winner
            labels = {"A": "сил света", "B": "сил тьмы"}
            enemy = "B" if self.team == "A" else "A"
            if winner == self.team:
                text = f"ПОБЕДА! Трон {labels.get(enemy, 'врага')} разрушен"
                color = (140, 255, 160)
            else:
                text = "ПОРАЖЕНИЕ. Ваш трон пал"
                color = (255, 120, 120)
            # Экран матча рисует UI, поэтому старый статус убираем.
            self.status_message = ""
            self.console.log(text, color)

    # ---------- сетевые снапшоты ----------
    def _update_net_view(self) -> None:
        if not self.snaps:
            return

        latest = self.snaps[-1].data
        players = latest.get("players", {})
        self.online_players = len(players) if isinstance(players, dict) else 0
        me = players.get(self.player_id) if self.player_id else None
        if me:
            if me.get("hero") is not None:
                self.hero_uid = int(me["hero"])
            self.gold = int(me.get("gold", 0))
            self.cs = int(me.get("cs", 0))
            self.denies = int(me.get("denies", 0))
            self.kills = int(me.get("kills", 0))
            self.deaths = int(me.get("deaths", 0))
            self.assists = int(me.get("assists", 0))
            self.level = int(me.get("level", 1))
            self.xp = float(me.get("xp", 0.0))
            self.xp_next = float(me.get("xp_next", 100.0))
            self.str = float(me.get("str", 0.0))
            self.agi = float(me.get("agi", 0.0))
            self.int = float(me.get("int", 0.0))
            self.mana = float(me.get("mana", 0.0))
            self.max_mana = float(me.get("max_mana", 0.0))
            self.items = list(me.get("items", []))
            self.cooldowns = {
                int(slot): float(cd)
                for slot, cd in (me.get("cooldowns") or {}).items()
            }
            hero_id = me.get("hero_id")
            if hero_id in self.heroes:
                self.hero_id = hero_id
                self.selected_hero = hero_id
            self._setup_abilities()
            self.respawn_timer = float(me.get("respawn", 0.0))
        self.match_time = float(latest.get("time", 0.0))
        self.match_over = bool(latest.get("over", False))
        self.winner = latest.get("winner")

        render_t = time.monotonic() - INTERP_DELAY
        s0, s1 = self._pick_snapshots(render_t)

        prev_units = {u.get("id"): u for u in s0.data.get("units", [])}
        units: List[Unit] = []
        for u in s1.data.get("units", []):
            x = float(u.get("x", 0.0))
            y = float(u.get("y", 0.0))
            prev = prev_units.get(u.get("id"))
            if prev is not None and s1.t > s0.t:
                alpha = (render_t - s0.t) / (s1.t - s0.t)
                alpha = max(0.0, min(1.0, alpha))
                x = float(prev.get("x", x)) + (x - float(prev.get("x", x))) * alpha
                y = float(prev.get("y", y)) + (y - float(prev.get("y", y))) * alpha

            units.append(Unit(
                uid=int(u.get("id", 0)),
                team=u.get("team", "A"),
                kind=u.get("kind", "creep"),
                pos=(x, y),
                hp=float(u.get("hp", 0.0)),
                max_hp=float(u.get("max_hp", 1.0)),
                radius=float(u.get("radius", 0.35)),
                atk_range=float(u.get("range", 1.5)),
                melee=bool(u.get("melee", False)),
                neutral_type=str(u.get("neutral_type", "")),
                alive=bool(u.get("alive", True)),
                atk_dmg=float(u.get("dmg", 0.0)),
                speed=float(u.get("speed", 0.0)),
                armor=float(u.get("armor", 0.0)),
            ))

        self.units = units
        self.hero = next((u for u in units if u.uid == self.hero_uid), None)

        prev_proj = {p.get("id"): p for p in s0.data.get("projectiles", [])}
        projectiles: List[ProjectileView] = []
        for p in s1.data.get("projectiles", []):
            x = float(p.get("x", 0.0))
            y = float(p.get("y", 0.0))
            prev = prev_proj.get(p.get("id"))
            if prev is not None and s1.t > s0.t:
                alpha = (render_t - s0.t) / (s1.t - s0.t)
                alpha = max(0.0, min(1.0, alpha))
                x = float(prev.get("x", x)) + (x - float(prev.get("x", x))) * alpha
                y = float(prev.get("y", y)) + (y - float(prev.get("y", y))) * alpha
            color = p.get("color", [255, 240, 150])
            projectiles.append(ProjectileView(
                pos=(x, y),
                color=tuple(color) if isinstance(color, (list, tuple)) else (255, 240, 150),
                radius=int(p.get("r", 4)),
            ))
        self.projectiles = projectiles

    def _pick_snapshots(self, render_t: float) -> Tuple[Snapshot, Snapshot]:
        snaps = list(self.snaps)
        for i in range(len(snaps) - 1):
            a, b = snaps[i], snaps[i + 1]
            if a.t <= render_t <= b.t:
                return a, b
        if render_t < snaps[0].t:
            return snaps[0], snaps[0]
        return snaps[-1], snaps[-1]

    # ---------- ввод ----------
    def _center_camera_on_team_spawn(self) -> None:
        if self.hero is not None:
            pos = self.hero.pos
        else:
            pos = self.spawns.get(self.team, (Grid.grid_w / 2, Grid.grid_h / 2))

        wx, wy = Grid.to_screen(*pos)
        self.camera.x = wx - self.screen.get_width() / 2
        self.camera.y = wy - self.screen.get_height() / 2
        self.camera.clamp_to_world(self.screen.get_width(), self.screen.get_height())

    def _clamp_camera(self) -> None:
        self.camera.clamp_to_world(self.screen.get_width(), self.screen.get_height())

    def set_zoom(self, value: float) -> None:
        value = max(0.5, min(8.0, float(value)))
        Grid.zoom = value
        self._center_camera_on_team_spawn()

    def set_fullscreen(self, value: bool) -> None:
        if value != self.is_fullscreen:
            self.toggle_fullscreen()

    def center_camera(self) -> None:
        self._center_camera_on_team_spawn()

    def toggle_fullscreen(self) -> None:
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            info = pygame.display.Info()
            self.screen = pygame.display.set_mode(
                (info.current_w, info.current_h), pygame.FULLSCREEN
            )
        else:
            self.screen = pygame.display.set_mode((self.windowed_w, self.windowed_h))

        self._clamp_camera()
        self.ui.screen = self.screen

    def _send_cmd(self, cmd: dict) -> None:
        if self.net_mode:
            if self.disconnected or not self.net:
                return
            self._seq += 1
            try:
                self.net.send_command(self._seq, cmd)
            except (ConnectionError, OSError):
                self.disconnected = True
                self.status_message = "Соединение потеряно"
        elif self.world:
            self.world.apply_command(self.player_id, cmd)

    # ---------- лобби/меню ----------
    def lobby_ip(self) -> str:
        if self.is_host and self.lan_ip:
            return f"{self.lan_ip}:{self.port}"
        return self.server_addr or f"127.0.0.1:{self.port}"

    def connect_net(self, host: str, port: int) -> bool:
        if self.net:
            self.net.close()
        self.net = None
        self.net_mode = True
        self.disconnected = False
        self.snaps.clear()
        self.state = "lobby"
        self.menu_message = f"Подключение к {host}:{port}..."

        try:
            self._connect(host, port, self.player_name)
        except Exception as exc:
            if self.net:
                self.net.close()
            self.net = None
            self.net_mode = False
            self.state = "menu"
            self.menu_message = str(exc)
            return False

        self.port = port
        self.menu_ip = host
        self.state = "lobby"
        self.is_host = self.host_id == self.player_id
        self._setup_abilities()
        self.console.log(
            f"connected to {host}:{port} as {self.player_id}",
            (120, 220, 150),
        )
        try:
            self.net.send({"type": "select_hero", "hero": self.selected_hero})
        except (ConnectionError, OSError):
            self.disconnected = True
        return True

    def start_host_lobby(self) -> bool:
        from server import start_background_server

        if self.local_server_thread is not None and self.local_server_thread.is_alive():
            self.port = self.local_server_port
        else:
            last_error = None
            for candidate in range(self.port, self.port + 5):
                try:
                    thread = start_background_server("0.0.0.0", candidate)
                    self.local_server_thread = thread
                    self.local_server_port = candidate
                    self.port = candidate
                    break
                except Exception as exc:
                    last_error = exc
            else:
                self.menu_message = f"Не удалось поднять сервер: {last_error}"
                return False

        self.lan_ip = lan_ip()
        if not self.connect_net("127.0.0.1", self.port):
            return False

        self.menu_message = f"Лобби создано. IP: {self.lan_ip}:{self.port}"
        return True

    def join_lobby(self, host: str, port: int) -> bool:
        self.menu_message = f"Подключение к {host}:{port}..."
        return self.connect_net(host, port)

    def leave_lobby(self) -> None:
        if self.net:
            self.net.close()
        self.net = None
        self.net_mode = False
        self.state = "menu"
        self.lobby = {}
        self.disconnected = False
        self.menu_message = "Вы вышли из лобби"

    def toggle_ready(self) -> None:
        if not self.net or self.state != "lobby":
            return
        me = next(
            (p for p in self.lobby.get("players", []) if p.get("id") == self.player_id),
            None,
        )
        ready = not bool(me and me.get("ready"))
        try:
            self.net.send({"type": "ready", "ready": ready})
        except (ConnectionError, OSError):
            self.disconnected = True

    def start_match(self) -> None:
        if not self.net or not self.is_host:
            return
        try:
            self.net.send({"type": "start"})
        except (ConnectionError, OSError):
            self.disconnected = True

    # ---------- магазин/способности ----------
    def toggle_shop(self) -> None:
        self.shop_open = not self.shop_open
        self.pending_ability = None
        self.shop_message = ""

    def shop_click(self, pos: Tuple[int, int]) -> None:
        item_id = self.ui.shop_hit(pos)
        if not item_id:
            return
        self._send_cmd({"type": "buy", "item": item_id})

    def cast_ability(self, slot: int) -> None:
        if self.state != "game" or self.match_over:
            return
        if slot < 0 or slot >= len(self.abilities):
            return
        ability = self.abilities[slot]
        if self.cooldowns.get(slot, 0.0) > 0:
            self.status_message = "Способность ещё на кулдауне"
            return
        if self.mana < float(ability.get("mana", 0)):
            self.status_message = "Недостаточно маны"
            return
        atype = ability.get("type")
        if atype == "target_damage":
            self.pending_ability = slot
            self.shop_open = False
            self.status_message = f"Выбери цель: {ability.get('name')}"
        elif atype == "aoe_damage":
            self.pending_ability = slot
            self.shop_open = False
            self.status_message = f"Выбери точку: {ability.get('name')}"
        else:
            self._send_cmd({"type": "cast", "slot": slot})

    def ability_click(self) -> None:
        if self.pending_ability is None or self.state != "game" or self.match_over:
            return
        slot = self.pending_ability
        ability = self.abilities[slot]
        mx, my = pygame.mouse.get_pos()
        wx = mx + self.camera.x
        wy = my + self.camera.y
        gx, gy = Grid.to_grid(wx, wy)

        if ability.get("type") == "target_damage":
            target = None
            best = 1.0
            for unit in self.units:
                if not unit.alive or unit.team == self.team:
                    continue
                d = dist((gx, gy), unit.pos)
                if d < best:
                    best = d
                    target = unit
            if target is None:
                self.status_message = "Цель не выбрана"
                return
            self._send_cmd({"type": "cast", "slot": slot, "target": target.uid})
        else:
            self._send_cmd({"type": "cast", "slot": slot, "x": gx, "y": gy})
        self.pending_ability = None
        self.status_message = ""

    def command_click(self) -> None:
        if self.match_over:
            return

        self.pending_ability = None
        mx, my = pygame.mouse.get_pos()
        wx = mx + self.camera.x
        wy = my + self.camera.y
        gx, gy = Grid.to_grid(wx, wy)

        target = None
        deny = False
        best_d = 1.0

        for unit in self.units:
            if not unit.alive:
                continue
            is_deny = False
            if unit.team == self.team:
                if unit.kind in ("creep", "creep_ranged") and unit.hp <= 0.4 * unit.max_hp:
                    is_deny = True
                else:
                    continue
            d = dist((gx, gy), unit.pos)
            if d < best_d:
                best_d = d
                target = unit
                deny = is_deny

        if target is not None:
            self.attack_marker_uid = target.uid
            self.move_marker = None
            self._send_cmd({
                "type": "deny" if deny else "attack",
                "target": target.uid,
            })
        else:
            if 0 <= gx <= Grid.grid_w and 0 <= gy <= Grid.grid_h:
                self.move_marker = (gx, gy)
                self.attack_marker_uid = None
                self._send_cmd({"type": "move", "x": gx, "y": gy})

    def command_stop(self) -> None:
        if self.match_over:
            return

        self.move_marker = None
        self.attack_marker_uid = None
        self._send_cmd({"type": "stop"})

    def handle_input(self, dt: float) -> None:
        # Пока консоль открыта, камера и мышь не должны реагировать.
        if getattr(self, "console", None) and self.console.open:
            return

        keys = pygame.key.get_pressed()
        cam_dx = 0
        cam_dy = 0
        speed = self.camera.scroll_speed * dt

        if keys[pygame.K_LEFT]:
            cam_dx -= speed
        if keys[pygame.K_RIGHT]:
            cam_dx += speed
        if keys[pygame.K_UP]:
            cam_dy -= speed
        if keys[pygame.K_DOWN]:
            cam_dy += speed

        if cam_dx != 0 or cam_dy != 0:
            self.camera.move(cam_dx, cam_dy)
            self._clamp_camera()

        if self._mmb_down:
            mx, my = pygame.mouse.get_pos()
            dx = mx - self._mmb_last[0]
            dy = my - self._mmb_last[1]
            self.camera.x -= dx
            self.camera.y -= dy
            self._mmb_last = (mx, my)
            self._clamp_camera()

    def _update_markers(self) -> None:
        if self.move_marker is not None:
            if not self.hero or not self.hero.alive or dist(self.hero.pos, self.move_marker) < 0.2:
                self.move_marker = None

        if self.attack_marker_uid is not None:
            target = next(
                (u for u in self.units if u.uid == self.attack_marker_uid and u.alive),
                None,
            )
            if target is None:
                self.attack_marker_uid = None

    # ---------- обновление ----------
    def _update_ping(self, dt: float) -> None:
        if self.net_mode and not self.disconnected and self.net:
            self._ping_timer += dt
            if self._ping_timer >= 2.0:
                self._ping_timer = 0.0
                try:
                    self.net.send_ping()
                except (ConnectionError, OSError):
                    self.disconnected = True
                    self.status_message = "Соединение потеряно"

    def update(self, dt: float) -> None:
        if self.net_mode:
            self._pump_net()

        if self.state != "game":
            self._update_ping(dt)
            return

        self.handle_input(dt)

        if self.net_mode:
            self._update_net_view()
        elif self.world:
            self.world.tick(dt)
            self._sync_offline_world()
            events = self.world.events
            if events:
                self.world.events = []
                for event in events:
                    self._handle_event(event)

        self._update_markers()

        for ft in self.floating_texts:
            ft.update(dt)
        self.floating_texts = [ft for ft in self.floating_texts if ft.lifetime > 0]

        for effect in self.ability_effects:
            effect.update(dt)
        self.ability_effects = [e for e in self.ability_effects if e.lifetime > 0]

        for effect in self.melee_effects:
            effect.update(dt)
        self.melee_effects = [e for e in self.melee_effects if e.lifetime > 0]

        self._update_ping(dt)

    # ---------- отрисовка ----------
    def _tile(self, surface, gx, gy, color, size=1.0):
        cx, cy = Grid.to_screen(gx, gy)
        cx, cy = self.camera.apply(cx, cy)
        w = Grid.tile_size * size * Grid.zoom
        h = Grid.tile_size * size * Grid.zoom
        pygame.draw.rect(surface, color, (cx, cy, w, h))

    def draw_debug_grid(self, surface):
        if not self.show_grid:
            return

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

        for i in range(Grid.grid_w + 1):
            x1, y1 = self.camera.apply(*Grid.to_screen(i, 0))
            x2, y2 = self.camera.apply(*Grid.to_screen(i, Grid.grid_h))
            pygame.draw.line(overlay, self.grid_color, (x1, y1), (x2, y2), 1)

        for i in range(Grid.grid_h + 1):
            x1, y1 = self.camera.apply(*Grid.to_screen(0, i))
            x2, y2 = self.camera.apply(*Grid.to_screen(Grid.grid_w, i))
            pygame.draw.line(overlay, self.grid_color, (x1, y1), (x2, y2), 1)

        surface.blit(overlay, (0, 0))

        for i in range(Grid.grid_w):
            if i % 2 == 0:
                cx, cy = Grid.to_screen(i + 0.5, 0.5)
                cx, cy = self.camera.apply(cx, cy)
                text = self.ui.small_font.render(str(i), True, self.text_color)
                surface.blit(text, (cx - text.get_width() // 2, cy - 5))

        for i in range(Grid.grid_h):
            if i % 2 == 0:
                cx, cy = Grid.to_screen(0.5, i + 0.5)
                cx, cy = self.camera.apply(cx, cy)
                text = self.ui.small_font.render(str(i), True, self.text_color)
                surface.blit(text, (cx - 5, cy - text.get_height() // 2))

    def draw_hitboxes(self, surface):
        if not self.show_hitboxes:
            return

        for unit in self.units:
            if not unit.alive:
                continue

            sx, sy = Grid.to_screen(unit.pos[0], unit.pos[1])
            sx, sy = self.camera.apply(sx, sy)
            radius_px = unit.radius * Grid.tile_size * Grid.zoom
            color = (255, 255, 0)

            surf = pygame.Surface(
                (int(radius_px * 2 + 4), int(radius_px * 2 + 4)),
                pygame.SRCALPHA,
            )
            pygame.draw.circle(
                surf, (*color, 60),
                (int(radius_px + 2), int(radius_px + 2)),
                int(radius_px),
            )
            pygame.draw.circle(
                surf, (*color, 200),
                (int(radius_px + 2), int(radius_px + 2)),
                int(radius_px), 1,
            )

            surface.blit(surf, (sx - radius_px - 2, sy - radius_px - 2))

    def draw_map(self, surface):
        c = self.colors
        tile = Grid.tile_size * Grid.zoom
        sw, sh = surface.get_size()
        gx0 = max(0, int(self.camera.x // tile) - 1)
        gx1 = min(Grid.grid_w, int((self.camera.x + sw) // tile) + 2)
        gy0 = max(0, int(self.camera.y // tile) - 1)
        gy1 = min(Grid.grid_h, int((self.camera.y + sh) // tile) + 2)

        for gx in range(gx0, gx1):
            for gy in range(gy0, gy1):
                col = c["grass"] if (gx + gy) % 2 == 0 else c["grass2"]
                self._tile(surface, gx, gy, col, 1.0)

        # Река по главной диагонали: из левого верхнего в правый нижний угол.
        river_color = c.get("river", (28, 86, 132))
        river_color2 = c.get("river2", (34, 100, 150))
        wave_color = c.get("river_wave", (95, 175, 220))
        for gx in range(gx0, gx1):
            for gy in range(gy0, gy1):
                cx = gx + 0.5
                cy = gy + 0.5
                if abs(cx - cy) <= 1.15:
                    col = river_color if (gx + gy) % 2 == 0 else river_color2
                    self._tile(surface, gx, gy, col, 1.0)
                    if (gx * 7 + gy * 3) % 9 == 0:
                        self._tile(surface, gx + 0.25, gy + 0.4, wave_color, 0.18)

        for path in self.lanes.values():
            for i in range(len(path) - 1):
                x1, y1 = path[i]
                x2, y2 = path[i + 1]
                steps = int(dist((x1, y1), (x2, y2)) * 4)
                for s in range(steps + 1):
                    t = s / max(1, steps)
                    gx = x1 + (x2 - x1) * t
                    gy = y1 + (y2 - y1) * t
                    self._tile(surface, gx - 0.4, gy - 0.4, c["lane"], 0.8)

        self._tile(surface, self.bases["A"][0] - 1, self.bases["A"][1] - 1, c["base_a"], 2.0)
        self._tile(surface, self.bases["B"][0] - 1, self.bases["B"][1] - 1, c["base_b"], 2.0)

    def draw_unit(self, surface, unit: Unit):
        sx, sy = Grid.to_screen(unit.pos[0], unit.pos[1])
        sx, sy = self.camera.apply(sx, sy)
        if unit.kind == "hero":
            base_r = 14
        elif unit.kind == "tower":
            base_r = 16
        elif unit.kind == "throne":
            base_r = 30
        elif unit.kind == "creep_ranged":
            base_r = 8
        elif unit.kind == "neutral":
            base_r = 10
        else:
            base_r = 9
        r = base_r * Grid.zoom * 0.7

        c = self.colors
        if unit.kind == "hero":
            color = c["hero"]
        elif unit.kind == "tower":
            color = c["tower_a"] if unit.team == "A" else c["tower_b"]
        elif unit.kind == "throne":
            color = c["base_a"] if unit.team == "A" else c["base_b"]
            if not unit.alive:
                color = (70, 70, 70)
        elif unit.kind == "creep_ranged":
            color = c.get("creep_ranged_a", c["creep_a"]) if unit.team == "A" else c.get("creep_ranged_b", c["creep_b"])
        elif unit.kind == "neutral":
            color = (190, 170, 120)
        else:
            color = c["creep_a"] if unit.team == "A" else c["creep_b"]

        sprite_rect = None
        if unit.kind in ("creep", "creep_ranged"):
            sprite_size = int((18 if unit.kind == "creep" else 15) * Grid.zoom)
            sprite = self._get_creep_sprite(unit.team, sprite_size)
            if sprite is not None:
                # У спрайтов уже есть мягкая тень, второй овал не нужен.
                sprite_rect = sprite.get_rect(
                    midbottom=(int(sx), int(sy + sprite_size * 0.12))
                )
                surface.blit(sprite, sprite_rect)
        elif unit.kind == "neutral":
            sprite_size = int(20 * Grid.zoom)
            sprite = self._get_neutral_sprite(unit.neutral_type, sprite_size)
            if sprite is not None:
                sprite_rect = sprite.get_rect(
                    midbottom=(int(sx), int(sy + sprite_size * 0.12))
                )
                surface.blit(sprite, sprite_rect)

        if sprite_rect is None:
            if unit.kind == "throne":
                self._draw_throne(surface, unit, sx, sy, r, color)
            else:
                pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy) + 3), int(r))
                pygame.draw.circle(surface, color, (int(sx), int(sy)), int(r))

            bw, bh = r * 2, 4
            bx = sx - r
            by = sy - r - 10
        else:
            bw = sprite_rect.width * 0.8
            bh = 4
            bx = sprite_rect.centerx - bw / 2
            by = sprite_rect.top - 8

        pygame.draw.rect(surface, c["hp_bg"], (int(bx), int(by), int(bw), bh))
        frac = max(0.0, min(1.0, unit.hp / max(1.0, unit.max_hp)))
        col = c["hp_a"] if unit.team == "A" else c["hp_b"]
        pygame.draw.rect(surface, col, (int(bx), int(by), int(bw * frac), bh))

        if unit.kind == "throne":
            if unit.alive:
                label_text = "СВЕТ" if unit.team == "A" else "ТЬМА"
                label_color = (255, 255, 255)
            else:
                label_text = "РУИНЫ"
                label_color = (170, 170, 170)
            label = self.ui.small_font.render(label_text, True, label_color)
            surface.blit(label, (int(sx - label.get_width() // 2), int(by - 15)))

    def _draw_throne(self, surface, unit: Unit, sx, sy, r, color):
        r = int(r)
        # Тень под троном.
        pygame.draw.ellipse(
            surface, (0, 0, 0, 90),
            (int(sx - r * 0.9), int(sy - r * 0.25 + 8), int(r * 1.8), int(r * 0.7)),
        )

        points = [
            (int(sx), int(sy - r)),
            (int(sx + r * 0.8), int(sy)),
            (int(sx), int(sy + r)),
            (int(sx - r * 0.8), int(sy)),
        ]
        pygame.draw.polygon(surface, color, points)
        outline = (255, 215, 0) if unit.alive else (105, 105, 105)
        pygame.draw.polygon(surface, outline, points, max(2, int(Grid.zoom)))

        inner = [
            (int(sx), int(sy - r * 0.55)),
            (int(sx + r * 0.42), int(sy)),
            (int(sx), int(sy + r * 0.55)),
            (int(sx - r * 0.42), int(sy)),
        ]
        brighter = tuple(min(255, int(v) + 35) for v in color)
        pygame.draw.polygon(surface, brighter, inner)

        if unit.alive:
            crown = [
                (int(sx - r * 0.24), int(sy - r * 0.55)),
                (int(sx - r * 0.13), int(sy - r * 0.82)),
                (int(sx), int(sy - r * 0.62)),
                (int(sx + r * 0.13), int(sy - r * 0.82)),
                (int(sx + r * 0.24), int(sy - r * 0.55)),
            ]
            pygame.draw.polygon(surface, (255, 215, 0), crown)

    def draw_camp_markers(self, surface):
        tile = Grid.tile_size * Grid.zoom
        for camp in self.map_cfg.get("neutrals", []):
            pos = camp.get("pos")
            if not pos:
                continue
            sx, sy = Grid.to_screen(float(pos[0]), float(pos[1]))
            sx, sy = self.camera.apply(sx, sy)
            radius = max(6, int(tile * 0.52))
            pygame.draw.circle(surface, (88, 76, 48, 42), (int(sx), int(sy)), radius)
            pygame.draw.circle(surface, (150, 130, 80, 90), (int(sx), int(sy)), radius, 1)

        for pos in self.map_cfg.get("runes", []):
            sx, sy = Grid.to_screen(float(pos[0]), float(pos[1]))
            sx, sy = self.camera.apply(sx, sy)
            radius = max(5, int(tile * 0.35))
            pygame.draw.circle(surface, (120, 220, 255, 80), (int(sx), int(sy)), radius)
            pygame.draw.circle(surface, (190, 245, 255, 220), (int(sx), int(sy)), radius, 2)

    def draw_world(self, surface):
        self.draw_map(surface)
        self.draw_camp_markers(surface)
        self.draw_debug_grid(surface)
        self.draw_hitboxes(surface)

        # Радиусы атаки вышек — только пока зажат Alt.
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LALT] or keys[pygame.K_RALT]:
            for unit in self.units:
                if not unit.alive or unit.kind != "tower":
                    continue
                sx, sy = Grid.to_screen(unit.pos[0], unit.pos[1])
                sx, sy = self.camera.apply(sx, sy)
                radius_px = int(unit.atk_range * Grid.tile_size * Grid.zoom)
                color = (255, 50, 50, 40) if unit.team == "B" else (50, 100, 255, 40)
                pygame.draw.circle(surface, color, (int(sx), int(sy)), radius_px)
                pygame.draw.circle(surface, (*color[:3], 120), (int(sx), int(sy)), radius_px, 2)

        if self.move_marker is not None:
            mx, my = Grid.to_screen(*self.move_marker)
            mx, my = self.camera.apply(mx, my)
            pygame.draw.circle(surface, (255, 255, 100), (int(mx), int(my)), 6, 2)
            pygame.draw.circle(surface, (255, 255, 100), (int(mx), int(my)), 2)

        if self.attack_marker_uid is not None:
            target = next(
                (u for u in self.units if u.uid == self.attack_marker_uid and u.alive),
                None,
            )
            if target is not None:
                sx, sy = Grid.to_screen(target.pos[0], target.pos[1])
                sx, sy = self.camera.apply(sx, sy)
                pygame.draw.circle(surface, (255, 80, 80), (int(sx), int(sy)), 20, 2)

        for effect in self.ability_effects:
            sx, sy = Grid.to_screen(effect.x, effect.y)
            sx, sy = self.camera.apply(sx, sy)
            progress = 1.0 - max(0.0, effect.lifetime) / max(0.001, effect.max_lifetime)
            base_r = max(10.0, effect.radius * Grid.tile_size * Grid.zoom)
            radius = int(base_r * (0.35 + 0.65 * progress))
            alpha = int(180 * (effect.lifetime / max(0.001, effect.max_lifetime)))
            pygame.draw.circle(surface, (*effect.color, max(25, alpha // 5)),
                               (int(sx), int(sy)), radius)
            pygame.draw.circle(surface, (*effect.color, alpha),
                               (int(sx), int(sy)), radius, 2)

        for effect in self.melee_effects:
            sx, sy = Grid.to_screen(effect.x, effect.y)
            sx, sy = self.camera.apply(sx, sy)
            alpha = int(230 * (effect.lifetime / max(0.001, effect.max_lifetime)))
            radius = 24
            pygame.draw.arc(
                surface, (*effect.color, max(30, alpha)),
                (int(sx - radius), int(sy - radius), radius * 2, radius * 2),
                effect.angle - 0.9, effect.angle + 0.9, 3,
            )
            inner = 15
            pygame.draw.arc(
                surface, (*effect.color, max(20, alpha // 2)),
                (int(sx - inner), int(sy - inner), inner * 2, inner * 2),
                effect.angle - 0.7, effect.angle + 0.7, 2,
            )

        if self.pending_ability is not None and self.pending_ability < len(self.abilities):
            ability = self.abilities[self.pending_ability]
            color = tuple(ability.get("color", (255, 255, 255)))
            mx, my = pygame.mouse.get_pos()
            pygame.draw.circle(surface, (*color, 200), (mx, my), 12, 2)
            pygame.draw.circle(surface, (*color, 120), (mx, my), 4)

        for unit in sorted(self.units, key=lambda u: u.pos[1]):
            if unit.alive or unit.kind == "throne":
                self.draw_unit(surface, unit)

        for proj in self.projectiles:
            sx, sy = Grid.to_screen(proj.pos[0], proj.pos[1])
            sx, sy = self.camera.apply(sx, sy)
            pygame.draw.circle(surface, proj.color, (int(sx), int(sy)), proj.radius)

        self.ui.draw_floating_texts(surface)

    def draw(self):
        if self.state == "menu":
            self.menu.draw_menu(self.screen, self)
        elif self.state == "lobby":
            self.menu.draw_lobby(self.screen, self)
        elif self.state == "settings":
            self.menu.draw_settings(self.screen, self)
        else:
            self.screen.fill(self.colors["bg"])

            world = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            self.draw_world(world)
            self.screen.blit(world, (0, 0))

            if self.show_ui:
                self.ui.draw_minimap(self.screen)
                self.ui.draw_hud(self.screen)

            if self.shop_open:
                self.ui.draw_shop(self.screen)

            if self.scoreboard_open:
                self.ui.draw_scoreboard(self.screen)

            if self.match_over:
                self.ui.draw_match_end(self.screen)

        # Консоль рисуется поверх всего, даже если HUD выключен.
        if self.console.open:
            self.console.draw(self.screen)

        pygame.display.flip()

    # ---------- главный цикл ----------
    def run(self):
        running = True
        while running and not self.quit_requested:
            dt = self.clock.tick(self.fps) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                if event.type == pygame.KEYDOWN:
                    # Консоль открывается/закрывается поверх игры.
                    if event.key in (pygame.K_BACKQUOTE, pygame.K_F1):
                        self.console.toggle()
                        continue

                    if self.console.open:
                        self.console.handle_key(event)
                        continue

                    if self.state in ("menu", "lobby", "settings"):
                        if event.key == pygame.K_ESCAPE:
                            if self.state == "settings":
                                if self.settings_action:
                                    self.settings_action = None
                                else:
                                    self.state = "menu"
                            elif self.state == "lobby":
                                self.leave_lobby()
                            elif self.menu_ip_focus:
                                self.menu_ip_focus = False
                            else:
                                running = False
                        elif event.key == pygame.K_F11:
                            self.toggle_fullscreen()
                        elif event.key == pygame.K_o:
                            self.show_ui = not self.show_ui
                        else:
                            self.menu.handle_key(event, self)
                        continue

                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                    elif event.key == pygame.K_o:
                        self.show_ui = not self.show_ui
                    elif event.key == self.control_codes["stop"]:
                        self.command_stop()
                    elif event.key == self.control_codes["shop"]:
                        self.toggle_shop()
                    elif event.key == self.control_codes["ability_1"]:
                        self.cast_ability(0)
                    elif event.key == self.control_codes["ability_2"]:
                        self.cast_ability(1)
                    elif event.key == self.control_codes["ability_3"]:
                        self.cast_ability(2)
                    elif event.key == self.control_codes["ability_4"]:
                        self.cast_ability(3)
                    elif event.key == pygame.K_TAB:
                        self.scoreboard_open = not self.scoreboard_open
                    continue

                # Пока открыта консоль, не командуем героем мышью.
                if self.console.open and event.type in (
                    pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP
                ):
                    continue

                if self.state in ("menu", "lobby"):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.menu.handle_click(pygame.mouse.get_pos(), self)
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.shop_open:
                            self.shop_click(pygame.mouse.get_pos())
                        else:
                            self.ability_click()
                    if event.button == 3:
                        if self.shop_open:
                            self.shop_open = False
                        else:
                            self.command_click()
                    if event.button == 2:
                        self._mmb_down = True
                        self._mmb_last = pygame.mouse.get_pos()

                if event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 2:
                        self._mmb_down = False

            self.update(dt)
            self.draw()

        if self.net:
            self.net.close()
        pygame.quit()
        sys.exit()
