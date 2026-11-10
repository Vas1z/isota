import argparse
import logging
import socket
import sys

import pygame

from game import Game
from shared.protocol import DEFAULT_MAX_PLAYERS, DEFAULT_PORT


def _lan_ip() -> str:
    """Best-effort определение локального LAN-IP без отправки пакетов."""
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


def _wait_for_enter() -> None:
    """Чтобы окно консоли не закрывалось мгновенно при запуске двойным кликом."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("Нажми Enter, чтобы закрыть...")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="isota — 2D MOBA prototype")
    parser.add_argument("--host", action="store_true",
                        help="запустить LAN-сервер локально и сразу подключиться")
    parser.add_argument("--connect", metavar="HOST",
                        help="подключиться к LAN-серверу по IP/имени")
    parser.add_argument("--offline", action="store_true",
                        help="играть без сети (режим по умолчанию)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default="Player", help="имя игрока")
    parser.add_argument("--max-players", type=int, default=DEFAULT_MAX_PLAYERS,
                        help="игроков в матче для режима --host")
    args = parser.parse_args()

    if args.host and args.connect:
        parser.error("--host и --connect нельзя использовать вместе")
    if args.offline and (args.host or args.connect):
        parser.error("--offline нельзя сочетать с --host/--connect")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    mode = "offline"
    host = None

    if args.host:
        from server import start_background_server

        try:
            start_background_server("0.0.0.0", args.port, max_players=args.max_players)
        except Exception as exc:
            print(f"Не удалось запустить локальный сервер: {exc}")
            print(f"Скорее всего порт {args.port} занят или не разрешён.")
            print(f"Попробуй другой порт: python main.py --host --port {args.port + 1}")
            _wait_for_enter()
            pygame.quit()
            sys.exit(1)

        ip = _lan_ip()
        print(f"LAN-сервер запущен на порту {args.port}.", flush=True)
        print(f"IP этого компьютера: {ip}", flush=True)
        print(f"Второй игрок: python main.py --connect {ip} --port {args.port}", flush=True)
        print("Если не подключается — разреши Python в брандмауэре Windows (частная сеть).", flush=True)
        mode = "net"
        host = "127.0.0.1"

    elif args.connect:
        mode = "net"
        host = args.connect
        print(f"Подключение к {host}:{args.port}...")

    else:
        print("Оффлайн-режим. Для LAN: python main.py --host")

    try:
        game = Game(mode=mode, host=host, port=args.port, name=args.name)
    except Exception as exc:
        print(f"Не удалось запустить игру: {exc}")

        if mode == "net":
            print()
            print("Что проверить:")
            if args.host:
                print(f"  • Порт {args.port} занят? Запусти с другим портом:")
                print(f"      python main.py --host --port {args.port + 1}")
            else:
                print("  • На компьютере-хосте должен быть запущен сервер:")
                print("      python main.py --host")
                print("    или отдельно:")
                print("      python server.py")
                print(f"  • Подключение к хосту: python main.py --connect <IP-хоста> --port {args.port}")
                print("  • IP хоста можно узнать через ipconfig (IPv4-адрес).")
                print("  • Разреши Python в брандмауэре Windows для частной сети.")
            print("  • Для игры без сети: python main.py")

        _wait_for_enter()
        pygame.quit()
        sys.exit(1)

    game.run()


if __name__ == "__main__":
    main()
