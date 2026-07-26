"""CineOS — Main entry point for local controller services.

This is a convenience wrapper. The actual service entry points are:
  - Telegram bot:  python -m src.telegram
  - Supervisor:    python -m workers.supervisor.service
  - Render worker: python -m workers.render_worker.service
  - Voice worker:  python -m workers.voice_worker.service
  - Cloud bridge:  python -m workers.cloud_bridge

Usage:
  python src/main.py                  # starts Telegram bot (default)
  python src/main.py --service bot    # starts Telegram bot
  python src/main.py --help           # show help
"""
import argparse
import asyncio
import sys


def main():
    parser = argparse.ArgumentParser(description="CineOS local controller")
    parser.add_argument(
        "--service", "-s",
        choices=["bot", "supervisor", "render", "voice"],
        default="bot",
        help="Which local service to start (default: bot)",
    )
    args = parser.parse_args()

    if args.service == "bot":
        from src.telegram.__main__ import main as bot_main
        asyncio.run(bot_main())
    elif args.service == "supervisor":
        from workers.supervisor.service import main as supervisor_main
        asyncio.run(supervisor_main())
    elif args.service == "render":
        from workers.render_worker.service import main as render_main
        asyncio.run(render_main())
    elif args.service == "voice":
        from workers.voice_worker.service import main as voice_main
        asyncio.run(voice_main())


if __name__ == "__main__":
    main()
