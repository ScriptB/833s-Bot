from __future__ import annotations

import asyncio
import os
import signal
import logging

from aiohttp import web
from dotenv import load_dotenv

from .bot import GuardianBot
from .config import load_settings
from .logging_setup import setup_logging

log = logging.getLogger("guardian.render")


async def _start_web_server() -> web.AppRunner:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "833s-guardian"})

    app.router.add_get("/", health)
    app.router.add_get("/healthz", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    log.info("Health server listening on 0.0.0.0:%s", port)
    return runner


async def main_async() -> None:
    load_dotenv()
    settings = load_settings()
    setup_logging(settings.log_level)

    runner = await _start_web_server()

    bot = GuardianBot(settings)

    # Graceful shutdown (Render sends SIGTERM on deploy/stop)
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows / limited environments
            pass

    async with bot:
        bot_task = asyncio.create_task(bot.start(settings.token), name="guardian-bot")
        done, pending = await asyncio.wait(
            {bot_task, asyncio.create_task(stop_event.wait(), name="guardian-stop")},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_event.is_set():
            log.info("Shutdown signal received; closing bot...")
            await bot.close()

        for t in pending:
            t.cancel()

    await runner.cleanup()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
