"""Авторитетный LAN-сервер.

Запуск:
    python server.py --host 0.0.0.0 --port 8765

Сервер не импортирует pygame. Клиенты присылают только команды
(move/attack/stop), всё остальное считает и рассылает сервер.
"""

import argparse
import asyncio
import json
import logging
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
        # Освобождаем место, чтобы гарантированно положить сигнал остановки.
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
    """Одна комната = один матч. Пока поддерживаем одну комнату на процесс."""

    def __init__(self, data: dict, max_players: int = DEFAULT_MAX_PLAYERS):
        self.data = data
        self.max_players = max_players
        self.world = World(data)
        self.clients: dict[str, Client] = {}
        self._next_id = 1
        self.loop_task: Optional[asyncio.Task] = None

    # ----- подключение -----
    async def add_client(self, client: Client, name: str):
        if len(self.clients) >= self.max_players:
            return False, "room is full"

        player_id = f"p{self._next_id}"
        self._next_id += 1
        team = self._pick_team()

        client.player_id = player_id
        client.name = name
        client.team = team
        self.clients[player_id] = client
        client.writer_task = asyncio.create_task(client.writer_loop())

        self.world.add_player(player_id, team, name)

        client.push({
            "type": "welcome",
            "version": PROTOCOL_VERSION,
            "player_id": player_id,
            "team": team,
            "tick_rate": TICK_RATE,
            "snapshot_rate": SNAPSHOT_RATE,
            "max_players": self.max_players,
        })
        client.push({"type": "snap", "data": self.world.snapshot()})

        # Первый игрок запускает матч. Второй может подключиться позже.
        self.start_loop()

        LOG.info("%s joined as %s (team %s)", client.name, player_id, team)
        return True, None

    def _pick_team(self) -> str:
        a = sum(1 for p in self.world.players.values() if p.team == "A")
        b = sum(1 for p in self.world.players.values() if p.team == "B")
        return "A" if a <= b else "B"

    async def remove_client(self, player_id: str) -> None:
        client = self.clients.pop(player_id, None)
        if not client:
            return

        self.world.remove_player(player_id)
        client.stop()

        for other in self.clients.values():
            other.push({
                "type": "player_left",
                "player_id": player_id,
                "name": client.name,
            })

        LOG.info("%s (%s) disconnected", client.name, player_id)

        if not self.clients:
            # Матч без игроков не держим: следующий заход начнёт новый.
            self.world = World(self.data)
            self._next_id = 1

    def handle_command(self, player_id: str, cmd: dict) -> None:
        if player_id in self.clients:
            self.world.apply_command(player_id, cmd)

    # ----- игровой цикл -----
    def start_loop(self) -> None:
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self._match_loop())

    async def _match_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        tick_dt = 1.0 / TICK_RATE
        snapshot_every = max(1, int(round(TICK_RATE / SNAPSHOT_RATE)))
        tick = 0

        LOG.info("match loop started (tick=%s Hz)", TICK_RATE)
        try:
            while self.clients:
                tick += 1
                next_tick += tick_dt
                delay = next_tick - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)

                self.world.tick(tick_dt)

                # Снапшоты привязываем к номеру тика, а не к wall-clock:
                # иначе при 30 Гц и дрожании asyncio можно случайно
                # отправлять снапшот через тик.
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

                mtype = msg.get("type")
                if mtype == "cmd":
                    cmd = msg.get("cmd")
                    if isinstance(cmd, dict):
                        self.room.handle_command(client.player_id, cmd)
                elif mtype == "ping":
                    client.push({"type": "pong", "t": msg.get("t")})
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

    def run() -> None:
        try:
            asyncio.run(serve(host, port, ready=ready, max_players=max_players))
        except Exception:
            LOG.exception("background server failed")

    thread = threading.Thread(target=run, name="isota-server", daemon=True)
    thread.start()

    if not ready.wait(timeout=5.0):
        raise RuntimeError("server did not start (port busy or data error)")
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
