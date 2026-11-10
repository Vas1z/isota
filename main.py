import argparse
import logging
import sys

import pygame

from game import Game
from shared.protocol import DEFAULT_MAX_PLAYERS, DEFAULT_PORT


def main() -> None:
    parser = argparse.ArgumentParser(description="isota — 2D MOBA prototype")
    parser.add_argument("--host", action="store_true",
                        help="запустить LAN-сервер локально и сразу подключиться")
    parser.add_argument("--connect", metavar="HOST",
                        help="подключиться к LAN-серверу по IP/имени")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default="Player", help="имя игрока")
    parser.add_argument("--max-players", type=int, default=DEFAULT_MAX_PLAYERS,
                        help="игроков в матче для режима --host")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.host:
        # Сервер в фоновом потоке, клиент подключается к localhost.
        # Другие игроки в LAN подключаются к IP этого компьютера.
        from server import start_background_server
        start_background_server("0.0.0.0", args.port, max_players=args.max_players)
        print(f"LAN-сервер запущен на порту {args.port}.")
        print(f"Второй игрок: python main.py --connect <IP-хоста> --port {args.port}")
        mode = "net"
        host = "127.0.0.1"
    elif args.connect:
        mode = "net"
        host = args.connect
    else:
        mode = "offline"
        host = None

    try:
        game = Game(mode=mode, host=host, port=args.port, name=args.name)
    except Exception as exc:
        print(f"Не удалось запустить игру: {exc}")
        pygame.quit()
        sys.exit(1)

    game.run()


if __name__ == "__main__":
    main()
