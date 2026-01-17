from __future__ import annotations

from dotenv import load_dotenv

from .bot import GuardianBot
from .config import load_settings
from .logging_setup import setup_logging


def main() -> None:
    load_dotenv()
    settings = load_settings()
    setup_logging(settings.log_level)

    bot = GuardianBot(settings)
    bot.run(settings.token)


if __name__ == "__main__":
    main()
