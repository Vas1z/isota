"""Авторитетный LAN-сервер с лобби.

Запуск:
    python server.py --host 0.0.0.0 --port 8765

Сервер не импортирует pygame. Клиенты присылают только команды
(лобби и игровые), всё остальное считает и рассылает сервер.
"""

import argparse
import asyncio
import json
import logging
import socket
import threading
from typing import Optional

import loader
from shared.protocol import (
    DEFAULT_MAX_PLAYERS,
    DEFAULT_PORT,
    PROTOCOL_VERSION,
    SNAPSHOT_RATE,
    TICK_RATE,
)
from shared.sim import World

LOG = logging.getLogger("isota.server")


class Client:
    """Одно TCP-подключение с очередью исходящих сообщений."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.writer_task: Optional[asyncio.Task] = None
        self.player_id: Optional[str] = None
        self.name = ""
        self.team: Optional[str] = None
        self.hero_id: Optional[str] = None
        self.ready = False

    async def writer_loop(self) -> None:
        try:
            while True:
                msg = await self.queue.get()
                if msg is None:
                    break
                data = json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n"
                self.writer.write(data)
                await self.writer.drain()
        except (ConnectionError, OSError, RuntimeError, asyncio.CancelledError):
            pass
        except Exception:
            LOG.exception("writer crashed")
        finally:
            try:
                self.writer.close()
            except Exception:
                pass

    def push(self, msg: dict) -> None:
        # Медленный клиент не должен тормозить весь матч: дропаем самое старое.
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    def stop(self) -> None:
        try:
            while True:
                self.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


class Room:
    """Одна комната: лобби, выбор героев, затем матч."""

    def __init__(self, data: dict, max_players: int = DEFAULT_MAX_PLAYERS):
        self.data = data
        self.max_players = max_players
        self.clients: dict[str, Client] = {}
        self._next_id = 1
        self.loop_task: Optional[asyncio.Task] = None
        self.world: Optional[World] = None
        self.started = False
        self.host_id: Optional[str] = None

    # ----- лобби -----
    def lobby_state(self) -> dict:
        return {
            "type": "lobby",
            "host": self.host_id,
            "max_players": self.max_players,
            "started": self.started,
            "players": [
                {
                    "id": pid,
                    "name": c.name,
                    "team": c.team,
                    "hero": c.hero_id,
                    "ready": c.ready,
                    "host": pid == self.host_id,
                }
                for pid, c in sorted(self.clients.items())
            ],
        }

    def broadcast_lobby(self) -> None:
        message = self.lobby_state()
        for client in self.clients.values():
            client.push(message)

    async def add_client(self, client: Client, name: str):
        if self.started:
            return False, "match already started"
        if len(self.clients) >= self.max_players:
            return False, "room is full"

        player_id = f"p{self._next_id}"
        self._next_id += 1
        team = self._pick_team()

        client.player_id = player_id
        client.name = name
        client.team = team
        client.hero_id = None
        client.ready = False
        self.clients[player_id] = client
        client.writer_task = asyncio.create_task(client.writer_loop())

        if self.host_id is None:
            self.host_id = player_id

        client.push({
            "type": "welcome",
            "version": PROTOCOL_VERSION,
            "player_id": player_id,
            "team": team,
            "host": self.host_id,
            "tick_rate": TICK_RATE,
            "snapshot_rate": SNAPSHOT_RATE,
            "max_players": self.max_players,
            "heroes": list(self.data["heroes"]["heroes"].keys()),
        })
        self.broadcast_lobby()

        LOG.info("%s joined as %s (team %s)", client.name, player_id, team)
        return True, None

    def _pick_team(self) -> str:
        a = sum(1 for c in self.clients.values() if c.team == "A")
        b = sum(1 for c in self.clients.values() if c.team == "B")
        return "A" if a <= b else "B"

    def handle_message(self, player_id: str, msg: dict) -> None:
        client = self.clients.get(player_id)
        if not client:
            return

        if self.started:
            if msg.get("type") == "cmd" and isinstance(msg.get("cmd"), dict):
                self.world.apply_command(player_id, msg["cmd"])
            return

        mtype = msg.get("type")
        if mtype == "select_hero":
            hero_id = msg.get("hero")
            if hero_id in self.data["heroes"]["heroes"]:
                client.hero_id = hero_id
                self.broadcast_lobby()
        elif mtype == "ready":
            client.ready = bool(msg.get("ready", not client.ready))
            self.broadcast_lobby()
        elif mtype == "start":
            self.start_match(player_id)

    def start_match(self, requested_by: str) -> None:
        if self.started:
            return
        client = self.clients.get(requested_by)
        if client is None:
            return
        if requested_by != self.host_id:
            client.push({"type": "error", "message": "Только хост может начать матч"})
            return
        if len(self.clients) < 2:
            client.push({"type": "error", "message": "Нужен хотя бы один второй игрок"})
            return
        if not all(c.ready for c in self.clients.values()):
            client.push({"type": "error", "message": "Не все игроки готовы"})
            return

        heroes = self.data["heroes"]["heroes"]
        default_hero = next(iter(heroes))
        for c in self.clients.values():
            if c.hero_id not in heroes:
                c.hero_id = default_hero

        self.world = World(self.data)
        for pid, c in self.clients.items():
            self.world.add_player(pid, c.team, c.name, c.hero_id)

        self.started = True
        start_message = {
            "type": "match_start",
            "players": {
                pid: {"team": c.team, "hero": c.hero_id}
                for pid, c in self.clients.items()
            },
        }
        for c in self.clients.values():
            c.push(start_message)
            c.push({"type": "snap", "data": self.world.snapshot()})

        self.start_loop()
        LOG.info("match started: %s", ", ".join(
            f"{pid}={c.hero_id}" for pid, c in self.clients.items()
        ))

    async def remove_client(self, player_id: str) -> None:
        client = self.clients.pop(player_id, None)
        if not client:
            return

        if self.started and self.world:
            self.world.remove_player(player_id)

        client.stop()

        if self.host_id == player_id:
            self.host_id = next(iter(self.clients), None)

        if self.clients:
            if self.started:
                for other in self.clients.values():
                    other.push({
                        "type": "player_left",
                        "player_id": player_id,
                        "name": client.name,
                    })
            else:
                self.broadcast_lobby()
        else:
            # Пустая комната начинает с чистого лобби.
            self.world = None
            self.started = False
            self.host_id = None
            self._next_id = 1

        LOG.info("%s (%s) disconnected", client.name, player_id)

    # ----- игровой цикл -----
    def start_loop(self) -> None:
        if self.started and (self.loop_task is None or self.loop_task.done()):
            self.loop_task = asyncio.create_task(self._match_loop())

    async def _match_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        tick_dt = 1.0 / TICK_RATE
        snapshot_every = max(1, int(round(TICK_RATE / SNAPSHOT_RATE)))
        tick = 0

        LOG.info("match loop started (tick=%s Hz)", TICK_RATE)
        try:
            while self.clients and self.started and self.world:
                tick += 1
                next_tick += tick_dt
                delay = next_tick - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)

                self.world.tick(tick_dt)

                if tick % snapshot_every == 0:
                    message = {"type": "snap", "data": self.world.snapshot()}
                    if self.world.events:
                        message["events"] = list(self.world.events)
                        self.world.events.clear()
                    for client in self.clients.values():
                        client.push(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("match loop crashed")
        finally:
            self.loop_task = None
            LOG.info("match loop stopped")


class GameServer:
    def __init__(self, max_players: int = DEFAULT_MAX_PLAYERS):
        data = loader.load_all()
        loader.validate(data)
        self.data = data
        self.room = Room(data, max_players=max_players)

    async def handle_connection(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        client = Client(reader, writer)
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                return

            try:
                hello = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._reject(writer, "bad hello")
                return

            if hello.get("type") != "hello":
                await self._reject(writer, "hello expected")
                return
            if hello.get("version") != PROTOCOL_VERSION:
                await self._reject(writer, "protocol version mismatch")
                return

            name = str(hello.get("name", "Player")).strip()[:24] or "Player"
            ok, error = await self.room.add_client(client, name)
            if not ok:
                await self._reject(writer, error or "cannot join")
                return

            LOG.info("connection from %s accepted", peer)

            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

                if msg.get("type") == "ping":
                    client.push({"type": "pong", "t": msg.get("t")})
                else:
                    self.room.handle_message(client.player_id, msg)
        except (asyncio.TimeoutError, ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception:
            LOG.exception("connection handler crashed (%s)", peer)
        finally:
            if client.player_id:
                await self.room.remove_client(client.player_id)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    async def _reject(writer: asyncio.StreamWriter, reason: str) -> None:
        try:
            payload = json.dumps({"type": "error", "message": reason}) + "\n"
            writer.write(payload.encode("utf-8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def serve(host: str, port: int, ready: Optional[threading.Event] = None,
                max_players: int = DEFAULT_MAX_PLAYERS) -> None:
    server = GameServer(max_players=max_players)
    tcp = await asyncio.start_server(server.handle_connection, host, port)
    addresses = ", ".join(str(sock.getsockname()) for sock in tcp.sockets)
    LOG.info("listening on %s", addresses)
    if ready is not None:
        ready.set()

    async with tcp:
        await tcp.serve_forever()


def start_background_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                            max_players: int = DEFAULT_MAX_PLAYERS) -> threading.Thread:
    """Запускает сервер в фоновом потоке (для режима `main.py --host`)."""
    ready = threading.Event()
    errors: dict = {}

    def run() -> None:
        try:
            asyncio.run(serve(host, port, ready=ready, max_players=max_players))
        except Exception as exc:
            errors["error"] = exc
            LOG.exception("background server failed")

    thread = threading.Thread(target=run, name="isota-server", daemon=True)
    thread.start()

    if not ready.wait(timeout=5.0):
        reason = errors.get("error")
        raise RuntimeError(f"server did not start: {reason or 'timeout'}")

    if not thread.is_alive():
        reason = errors.get("error")
        raise RuntimeError(f"server stopped right after start: {reason or 'unknown error'}")

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"server is not accepting connections on 127.0.0.1:{port}: {exc}"
        ) from exc

    return thread


def main() -> None:
    parser = argparse.ArgumentParser(description="isota LAN server")
    parser.add_argument("--host", default="0.0.0.0", help="interface to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port")
    parser.add_argument("--max-players", type=int, default=DEFAULT_MAX_PLAYERS,
                        help="players per match (2 = 1v1, 4 = 2v2)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(serve(args.host, args.port, max_players=args.max_players))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
