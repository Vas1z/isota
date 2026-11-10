"""Простой TCP-клиент для LAN-протокола: JSON-строки, разделённые \\n."""

import json
import queue
import socket
import threading
import time
from typing import List

from shared.protocol import DEFAULT_PORT, PROTOCOL_VERSION


class NetClient:
    def __init__(self, host: str, port: int = DEFAULT_PORT, name: str = "Player",
                 connect_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.name = name
        self.connected = False
        self.rtt_ms = 0

        self._sock = socket.create_connection((host, port), timeout=connect_timeout)
        self._sock.settimeout(None)
        try:
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

        self._file = self._sock.makefile("rb")
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._send_lock = threading.Lock()
        self._closed = False

        self._send({
            "type": "hello",
            "version": PROTOCOL_VERSION,
            "name": name,
        })

        self._reader = threading.Thread(
            target=self._read_loop, name="isota-net-reader", daemon=True
        )
        self._reader.start()
        self.connected = True

    # ----- чтение -----
    def _read_loop(self) -> None:
        try:
            for line in self._file:
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                self._inbox.put(msg)
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            self.connected = False
            self._inbox.put({"type": "_disconnected"})

    def poll(self) -> List[dict]:
        messages = []
        while True:
            try:
                messages.append(self._inbox.get_nowait())
            except queue.Empty:
                break
        return messages

    # ----- отправка -----
    def _send(self, obj: dict) -> None:
        if self._closed:
            raise ConnectionError("client is closed")
        payload = json.dumps(obj, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._send_lock:
            self._sock.sendall(payload)

    def send(self, obj: dict) -> None:
        self._send(obj)

    def send_command(self, seq: int, cmd: dict) -> None:
        self._send({"type": "cmd", "seq": seq, "cmd": cmd})

    def send_ping(self) -> None:
        self._send({"type": "ping", "t": time.monotonic()})

    def close(self) -> None:
        self._closed = True
        self.connected = False
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            self._file.close()
        except OSError:
            pass
