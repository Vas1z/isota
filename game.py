import math
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

import loader
from console import Console
from netclient import NetClient
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


# Насколько клиент отстаёт от последнего снапшота. Даёт буфер для интерполяции.
INTERP_DELAY = 0.06


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

        self.cfg = self.data["settings"]
        self.controls = self.data["controls"]
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
        self.kills = 0
        self.deaths = 0
        self.respawn_timer = 0.0

        self.move_marker: Optional[Tuple[float, float]] = None
        self.attack_marker_uid: Optional[int] = None

        # --- подключение/симуляция до создания окна ---
        if self.net_mode:
            self._connect(host or "127.0.0.1", port, name)
        else:
            self._start_offline(name)

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
        self.console = Console(self)
        self._center_camera_on_team_spawn()

        if self.net_mode:
            self.console.log(
                f"connected to {self.server_addr} as {self.player_id} ({self.team})",
                (120, 220, 150),
            )
        else:
            self.console.log("offline mode", (150, 150, 150))
        self.console.log("press ~ or F1 to open this console", (150, 150, 150))

    # ---------- режимы ----------
    def _start_offline(self, name: str) -> None:
        self.world = World(self.data)
        self.world.add_player("local", "A", name)
        self.player_id = "local"
        self.team = "A"
        self.max_players = 1
        self.online_players = 1
        self.hero = self.world.players["local"].hero
        self.hero_uid = self.hero.uid
        self.units = self.world.units
        self._sync_offline_player()

    def _connect(self, host: str, port: int, name: str) -> None:
        self.net = NetClient(host, port, name)
        deadline = time.monotonic() + 5.0

        while time.monotonic() < deadline:
            for msg in self.net.poll():
                mtype = msg.get("type")
                if mtype == "welcome":
                    self.player_id = msg.get("player_id")
                    self.team = msg.get("team", "A")
                    self.max_players = int(msg.get("max_players", 2))
                    self.server_addr = f"{host}:{port}"
                    self.status_message = f"Онлайн: {host}:{port}"
                    return
                if mtype == "error":
                    self.net.close()
                    raise RuntimeError(msg.get("message", "server error"))
                if mtype == "_disconnected":
                    raise RuntimeError("server closed connection")
            time.sleep(0.01)

        self.net.close()
        raise RuntimeError("server did not send welcome")

    # ---------- состояние ----------
    def _sync_offline_player(self) -> None:
        if not self.world or not self.player_id:
            return
        player = self.world.players[self.player_id]
        self.hero = player.hero
        self.hero_uid = player.hero.uid
        self.gold = int(player.gold)
        self.cs = player.cs
        self.kills = player.kills
        self.deaths = player.deaths
        self.respawn_timer = player.respawn_timer
        self.match_time = self.world.match_time

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
                self.console.log(text, (255, 120, 120))

            elif mtype == "_disconnected":
                self.disconnected = True
                self._manual_ping = False
                self.status_message = "Соединение потеряно"
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
            self.kills = int(me.get("kills", 0))
            self.deaths = int(me.get("deaths", 0))
            self.respawn_timer = float(me.get("respawn", 0.0))
        self.match_time = float(latest.get("time", 0.0))

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

    def command_click(self) -> None:
        mx, my = pygame.mouse.get_pos()
        wx = mx + self.camera.x
        wy = my + self.camera.y
        gx, gy = Grid.to_grid(wx, wy)

        target = None
        best_d = 1.0
        for unit in self.units:
            if not unit.alive or unit.team == self.team:
                continue
            d = dist((gx, gy), unit.pos)
            if d < best_d:
                best_d = d
                target = unit

        if target is not None:
            self.attack_marker_uid = target.uid
            self.move_marker = None
            self._send_cmd({"type": "attack", "target": target.uid})
        else:
            if 0 <= gx <= Grid.grid_w and 0 <= gy <= Grid.grid_h:
                self.move_marker = (gx, gy)
                self.attack_marker_uid = None
                self._send_cmd({"type": "move", "x": gx, "y": gy})

    def command_stop(self) -> None:
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
    def update(self, dt: float) -> None:
        self.handle_input(dt)

        if self.net_mode:
            self._pump_net()
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

        if self.net_mode and not self.disconnected and self.net:
            self._ping_timer += dt
            if self._ping_timer >= 2.0:
                self._ping_timer = 0.0
                try:
                    self.net.send_ping()
                except (ConnectionError, OSError):
                    self.disconnected = True
                    self.status_message = "Соединение потеряно"

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
        for gx in range(Grid.grid_w):
            for gy in range(Grid.grid_h):
                col = c["grass"] if (gx + gy) % 2 == 0 else c["grass2"]
                self._tile(surface, gx, gy, col, 1.0)

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
        r = (14 if unit.kind == "hero" else 9 if unit.kind == "creep" else 16) * Grid.zoom * 0.7
        c = self.colors
        if unit.kind == "hero":
            color = c["hero"]
        elif unit.kind == "tower":
            color = c["tower_a"] if unit.team == "A" else c["tower_b"]
        else:
            color = c["creep_a"] if unit.team == "A" else c["creep_b"]

        pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy) + 3), int(r))
        pygame.draw.circle(surface, color, (int(sx), int(sy)), int(r))

        bw, bh = r * 2, 4
        bx = sx - r
        by = sy - r - 10
        pygame.draw.rect(surface, c["hp_bg"], (int(bx), int(by), int(bw), bh))
        frac = max(0.0, min(1.0, unit.hp / max(1.0, unit.max_hp)))
        col = c["hp_a"] if unit.team == "A" else c["hp_b"]
        pygame.draw.rect(surface, col, (int(bx), int(by), int(bw * frac), bh))

    def draw_world(self, surface):
        self.draw_map(surface)
        self.draw_debug_grid(surface)
        self.draw_hitboxes(surface)

        # Радиусы атаки вышек. Рисуем прямо на SRCALPHA-поверхности,
        # без гигантских кэшей на 100+ МБ.
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

        for unit in sorted(self.units, key=lambda u: u.pos[1]):
            if unit.alive:
                self.draw_unit(surface, unit)

        for proj in self.projectiles:
            sx, sy = Grid.to_screen(proj.pos[0], proj.pos[1])
            sx, sy = self.camera.apply(sx, sy)
            pygame.draw.circle(surface, proj.color, (int(sx), int(sy)), proj.radius)

        self.ui.draw_floating_texts(surface)

    def draw(self):
        self.screen.fill(self.colors["bg"])

        world = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        self.draw_world(world)
        self.screen.blit(world, (0, 0))

        if self.show_ui:
            self.ui.draw_minimap(self.screen)
            self.ui.draw_hud(self.screen)

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

                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                    elif event.key == pygame.K_o:
                        self.show_ui = not self.show_ui
                    elif event.key == pygame.K_s:
                        self.command_stop()
                    continue

                # Пока открыта консоль, не командуем героем мышью.
                if self.console.open and event.type in (
                    pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP
                ):
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 3:
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
