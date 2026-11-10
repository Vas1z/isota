"""Сетевые утилиты, общие для клиента и main.py."""

import socket


def lan_ip() -> str:
    """Best-effort локальный LAN-IP без отправки пакетов."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()
