"""CineOS Telegram Bot — Entry point for `python -m src.telegram`"""
import asyncio
import logging
import signal
import sys
from aiohttp import web

from src.telegram.bridge import CineOSTelegramBridge, create_bridge
from src.config import load_config

logger = logging.getLogger("cineos.telegram")

HEALTH_PORT = 8000
_startup_time = None


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint for Docker HEALTHCHECK."""
    return web.json_response({
        "status": "healthy",
        "service": "telegram_bot",
        "uptime_seconds": int(asyncio.get_event_loop().time() - _startup_time) if _startup_time else 0,
    })


async def run_health_server() -> web.AppRunner:
    """Start a lightweight health check HTTP server."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health server started on port %d", HEALTH_PORT)
    return runner


async def main():
    """Start the Telegram bot and health server."""
    global _startup_time
    _startup_time = asyncio.get_event_loop().time()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    config = load_config()
    bridge = create_bridge(config)
    health_runner = await run_health_server()

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    logger.info("Starting CineOS Telegram Bot")
    await bridge.start()
    logger.info("Telegram bot connected")

    await stop_event.wait()

    logger.info("Shutting down Telegram bot...")
    await bridge.stop()
    await health_runner.cleanup()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
