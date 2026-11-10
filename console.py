"""Внутриигровая dev-консоль.

Открывается по `~` (backquote) или F1. Пока консоль открыта, ввод игры
не обрабатывается: буквы уходят в командную строку.

Примеры:
    show_fps true
    show_ui false
    show_grid true
    show_hitboxes false
    ping
    zoom 2
    status
    players
    help
"""

import os
import subprocess
import sys
from pathlib import Path

import pygame


class Console:
    def __init__(self, game):
        self.game = game
        self.open = False
        self.text = ""
        self.lines = []          # (text, color)
        self.history = []
        self.history_index = 0
        self.max_lines = 300

        self.font = pygame.font.SysFont("consolas", 14)
        self.small = pygame.font.SysFont("consolas", 12)

        self._handlers = {
            "help": self._cmd_help,
            "commands": self._cmd_help,
            "show_fps": self._cmd_show_fps,
            "fps": self._cmd_show_fps,
            "show_ui": self._cmd_show_ui,
            "ui": self._cmd_show_ui,
            "show_grid": self._cmd_show_grid,
            "grid": self._cmd_show_grid,
            "show_hitboxes": self._cmd_show_hitboxes,
            "hitboxes": self._cmd_show_hitboxes,
            "debug": self._cmd_debug,
            "ping": self._cmd_ping,
            "net": self._cmd_net,
            "status": self._cmd_status,
            "players": self._cmd_players,
            "snap": self._cmd_snap,
            "thrones": self._cmd_thrones,
            "match": self._cmd_match,
            "reload_sprites": self._cmd_reload_sprites,
            "sprites": self._cmd_reload_sprites,
            "zoom": self._cmd_zoom,
            "center": self._cmd_center,
            "cam": self._cmd_center,
            "fullscreen": self._cmd_fullscreen,
            "clear": self._cmd_clear,
            "echo": self._cmd_echo,
            "history": self._cmd_history,
            "agents": self._cmd_agents,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }

        self._help = {
            "help": "показать этот список",
            "show_fps [on|off]": "показывать FPS в HUD",
            "show_ui [on|off]": "показывать HUD и миникарту",
            "show_grid [on|off]": "показать отладочную сетку",
            "show_hitboxes [on|off]": "показать хитбоксы юнитов",
            "debug [on|off]": "сетка + хитбоксы одной командой",
            "ping": "отправить ping и показать последний RTT",
            "net": "состояние соединения и снапшотов",
            "status": "режим, игрок, время, FPS, ping",
            "players": "список игроков и их золото/CS/K/D",
            "snap": "последний снапшот сервера",
            "thrones": "HP и состояние обоих тронов",
            "match": "состояние матча: идёт/победа/поражение",
            "reload_sprites": "перечитать assets/*.png без перезапуска",
            "zoom <0.5..8>": "масштаб карты",
            "center": "центрировать камеру на герое",
            "fullscreen [on|off]": "полноэкранный режим",
            "clear": "очистить консоль",
            "echo <text>": "вывести текст",
            "history": "история команд",
            "agents": "живой лог агентов в отдельном окне терминала",
            "quit": "выйти из игры",
        }

        self.log("isota console ready", (150, 220, 255))
        self.log("type 'help' for commands", (150, 150, 150))

    # ---------- открытие/закрытие ----------
    def toggle(self) -> None:
        if self.open:
            self.close()
        else:
            self.open = True
            self.text = ""
            self.history_index = len(self.history)
            # Включить автоповтор клавиш, чтобы можно было удерживать backspace.
            pygame.key.set_repeat(400, 35)
            self.log("console opened", (120, 180, 120))

    def close(self) -> None:
        if self.open:
            self.open = False
            pygame.key.set_repeat()

    # ---------- ввод ----------
    def handle_key(self, event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.close()
            return

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.execute(self.text)
            return

        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
            return

        if event.key == pygame.K_DELETE:
            self.text = ""
            return

        if event.key == pygame.K_UP:
            if self.history:
                if self.history_index > 0:
                    self.history_index -= 1
                self.text = self.history[self.history_index]
            return

        if event.key == pygame.K_DOWN:
            if self.history:
                if self.history_index < len(self.history):
                    self.history_index += 1
                if self.history_index >= len(self.history):
                    self.history_index = len(self.history)
                    self.text = ""
                else:
                    self.text = self.history[self.history_index]
            return

        if event.key == pygame.K_TAB:
            self._complete()
            return

        ch = event.unicode
        if ch and ch.isprintable() and len(self.text) < 200:
            self.text += ch

    def _complete(self) -> None:
        prefix = self.text.strip().lower()
        if not prefix or " " in prefix:
            return

        matches = sorted(name for name in self._handlers if name.startswith(prefix))
        if not matches:
            return

        if len(matches) == 1:
            self.text = matches[0] + " "
        else:
            common = os.path.commonprefix(matches)
            if common:
                self.text = common
            self.log("  ".join(matches), (150, 150, 150))

    # ---------- выполнение ----------
    def execute(self, raw: str) -> None:
        line = raw.strip()
        self.text = ""

        if not line:
            return

        self.history.append(line)
        self.history_index = len(self.history)
        self.log(f"> {line}", (120, 200, 255))

        parts = line.split()
        name = parts[0].lower()
        args = parts[1:]
        handler = self._handlers.get(name)

        if handler is None:
            self.log(f"unknown command: {name}. type 'help'", (255, 120, 120))
            return

        try:
            handler(args)
        except Exception as exc:
            self.log(f"error: {exc}", (255, 120, 120))

    # ---------- логи ----------
    def log(self, text, color=(220, 220, 220)) -> None:
        self.lines.append((str(text), color))
        if len(self.lines) > self.max_lines:
            del self.lines[: len(self.lines) - self.max_lines]

    # ---------- команды ----------
    def _bool_arg(self, args, current: bool) -> bool:
        if not args:
            return not current
        value = args[0].lower()
        if value in ("1", "true", "on", "yes", "y"):
            return True
        if value in ("0", "false", "off", "no", "n"):
            return False
        raise ValueError(f"expected true/false, got {args[0]!r}")

    def _cmd_help(self, args) -> None:
        self.log("commands:", (255, 255, 150))
        for name in sorted(self._help):
            self.log(f"  {name:<22} {self._help[name]}")

    def _cmd_show_fps(self, args) -> None:
        self.game.show_fps = self._bool_arg(args, self.game.show_fps)
        self.log(f"show_fps = {self.game.show_fps}", (150, 220, 150))

    def _cmd_show_ui(self, args) -> None:
        self.game.show_ui = self._bool_arg(args, self.game.show_ui)
        self.log(f"show_ui = {self.game.show_ui}", (150, 220, 150))

    def _cmd_show_grid(self, args) -> None:
        self.game.show_grid = self._bool_arg(args, self.game.show_grid)
        self.log(f"show_grid = {self.game.show_grid}", (150, 220, 150))

    def _cmd_show_hitboxes(self, args) -> None:
        self.game.show_hitboxes = self._bool_arg(args, self.game.show_hitboxes)
        self.log(f"show_hitboxes = {self.game.show_hitboxes}", (150, 220, 150))

    def _cmd_debug(self, args) -> None:
        value = self._bool_arg(args, self.game.show_grid)
        self.game.show_grid = value
        self.game.show_hitboxes = value
        self.log(f"debug = {value} (grid + hitboxes)", (150, 220, 150))

    def _cmd_ping(self, args) -> None:
        if not self.game.net_mode:
            self.log("ping: offline mode", (200, 200, 120))
            return
        if self.game.disconnected or not self.game.net:
            self.log("ping: not connected", (255, 120, 120))
            return
        try:
            self.game._manual_ping = True
            self.game.net.send_ping()
            self.log("ping sent...", (150, 220, 150))
        except (ConnectionError, OSError) as exc:
            self.game._manual_ping = False
            self.log(f"ping failed: {exc}", (255, 120, 120))

    def _cmd_net(self, args) -> None:
        if not self.game.net_mode:
            self.log("net: offline mode", (200, 200, 120))
            return
        connected = bool(self.game.net and self.game.net.connected and not self.game.disconnected)
        snapshots = len(self.game.snaps)
        latest_tick = "-"
        if self.game.snaps:
            latest_tick = self.game.snaps[-1].data.get("tick", "-")
        self.log(
            f"net: addr={self.game.server_addr} connected={connected} "
            f"ping={self.game.ping_ms}ms snapshots={snapshots} tick={latest_tick}"
        )

    def _cmd_status(self, args) -> None:
        game = self.game
        mode = "online" if game.net_mode else "offline"
        fps = int(game.clock.get_fps())
        ping = f"{game.ping_ms}ms" if game.net_mode else "-"
        self.log(
            f"mode={mode} player={game.player_id or '-'} team={game.team} "
            f"units={len(game.units)} time={game.match_time:.1f}s fps={fps} ping={ping}"
        )
        hero = game.hero
        if hero is not None:
            self.log(
                f"hero pos=({hero.pos[0]:.2f}, {hero.pos[1]:.2f}) "
                f"hp={hero.hp:.0f}/{hero.max_hp:.0f} alive={hero.alive} "
                f"level={game.level} xp={game.xp:.0f}/{game.xp_next:.0f} "
                f"gold={game.gold} cs={game.cs} k/d={game.kills}/{game.deaths}"
            )
        if game.net_mode:
            self.log(f"server={game.server_addr} disconnected={game.disconnected}")

    def _cmd_players(self, args) -> None:
        game = self.game
        players = None

        if game.net_mode:
            if game.snaps:
                players = game.snaps[-1].data.get("players")
        elif game.world is not None:
            players = {
                pid: {
                    "team": p.team,
                    "name": p.name,
                    "gold": int(p.gold),
                    "cs": p.cs,
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "respawn": p.respawn_timer,
                }
                for pid, p in game.world.players.items()
            }

        if not players:
            self.log("players: no data", (200, 200, 120))
            return

        for pid in sorted(players):
            p = players[pid]
            self.log(
                f"{pid} team={p.get('team', '?')} name={p.get('name', '')!r} "
                f"lvl={p.get('level', 1)} xp={float(p.get('xp', 0)):.0f}/{float(p.get('xp_next', 100)):.0f} "
                f"gold={p.get('gold', 0)} cs={p.get('cs', 0)} "
                f"k/d={p.get('kills', 0)}/{p.get('deaths', 0)} "
                f"respawn={float(p.get('respawn', 0)):.1f}s"
            )

    def _cmd_snap(self, args) -> None:
        game = self.game
        if game.net_mode:
            if not game.snaps:
                self.log("snap: no snapshots yet", (200, 200, 120))
                return
            snap = game.snaps[-1]
            data = snap.data
            self.log(
                f"snap: tick={data.get('tick', '-')} time={data.get('time', '-')} "
                f"units={len(data.get('units', []))} projectiles={len(data.get('projectiles', []))}"
            )
        elif game.world is not None:
            self.log(
                f"world: tick={game.world.tick_count} time={game.world.match_time:.2f} "
                f"units={len(game.world.units)} projectiles={len(game.world.projectiles)}"
            )

    def _cmd_reload_sprites(self, args) -> None:
        teams = self.game.reload_sprites()
        if teams:
            self.log(f"sprites loaded for teams: {', '.join(teams)}", (150, 220, 150))
        else:
            self.log("sprites: no files in assets/ (fallback circles)", (200, 200, 120))

    def _cmd_thrones(self, args) -> None:
        thrones = [u for u in self.game.units if u.kind == "throne"]
        if not thrones:
            self.log("thrones: no data", (200, 200, 120))
            return
        labels = {"A": "СВЕТ", "B": "ТЬМА"}
        for unit in thrones:
            self.log(
                f"{labels.get(unit.team, unit.team)} hp={unit.hp:.0f}/{unit.max_hp:.0f} "
                f"alive={unit.alive}"
            )

    def _cmd_match(self, args) -> None:
        game = self.game
        if game.match_over:
            self.log(f"match: over, winner={game.winner}, time={game.match_time:.1f}s")
        else:
            self.log(f"match: in progress, time={game.match_time:.1f}s")

    def _cmd_zoom(self, args) -> None:
        if not args:
            self.log(f"zoom = {self.game.Grid.zoom:.2f}", (150, 220, 150))
            return
        value = float(args[0])
        self.game.set_zoom(value)
        self.log(f"zoom = {self.game.Grid.zoom:.2f}", (150, 220, 150))

    def _cmd_center(self, args) -> None:
        self.game.center_camera()
        self.log("camera centered", (150, 220, 150))

    def _cmd_fullscreen(self, args) -> None:
        value = self._bool_arg(args, self.game.is_fullscreen)
        self.game.set_fullscreen(value)
        self.log(f"fullscreen = {self.game.is_fullscreen}", (150, 220, 150))

    def _cmd_clear(self, args) -> None:
        self.lines.clear()

    def _cmd_echo(self, args) -> None:
        self.log(" ".join(args))

    def _cmd_history(self, args) -> None:
        if not self.history:
            self.log("history is empty", (200, 200, 120))
            return
        for i, line in enumerate(self.history, 1):
            self.log(f"{i:>3}  {line}")

    def _cmd_agents(self, args) -> None:
        root = Path(__file__).parent
        viewer = root / "agents_console.py"
        if not viewer.exists():
            self.log("agents_console.py не найден", (255, 120, 120))
            return
        try:
            flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            subprocess.Popen(
                [sys.executable, str(viewer)],
                cwd=str(root),
                creationflags=flags,
            )
            self.log("лог агентов открыт в отдельном окне", (150, 220, 150))
        except OSError as exc:
            self.log(f"не удалось открыть лог агентов: {exc}", (255, 120, 120))

    def _cmd_quit(self, args) -> None:
        self.log("bye", (150, 220, 150))
        self.game.quit_requested = True
        self.close()

    # ---------- отрисовка ----------
    def _fit(self, text: str, max_width: int) -> str:
        if self.font.size(text)[0] <= max_width:
            return text
        suffix = "..."
        while text and self.font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix

    def draw(self, surface) -> None:
        width, height = surface.get_size()
        panel_h = min(max(240, height // 2), 420)
        input_y = panel_h - 30
        line_h = self.font.get_linesize()
        max_log_lines = max(1, (input_y - 30) // line_h)

        panel = pygame.Surface((width, panel_h), pygame.SRCALPHA)
        panel.fill((8, 10, 14, 232))
        pygame.draw.line(panel, (90, 105, 130), (0, panel_h - 1), (width, panel_h - 1), 1)

        header = self.small.render(
            "CONSOLE   ~ close   Enter run   Tab complete   Up/Down history",
            True, (110, 160, 205),
        )
        panel.blit(header, (12, 6))

        visible = self.lines[-max_log_lines:]
        y = 24
        for text, color in visible:
            line = self._fit(text, width - 24)
            panel.blit(self.font.render(line, True, color), (12, y))
            y += line_h

        pygame.draw.rect(panel, (14, 18, 24, 255), (0, input_y - 6, width, 36))
        pygame.draw.line(panel, (90, 105, 130), (0, input_y - 6), (width, input_y - 6), 1)

        cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
        prompt = self._fit("> " + self.text, width - 30) + cursor
        panel.blit(self.font.render(prompt, True, (240, 240, 240)), (12, input_y))

        surface.blit(panel, (0, 0))
