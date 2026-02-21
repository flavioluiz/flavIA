"""Bot runner utilities for managing multiple concurrent bot instances."""

import asyncio
import logging
from typing import Optional

from flavia.config import Settings
from flavia.config.bots import BotConfig

from .telegram_interface import TelegramBot

logger = logging.getLogger(__name__)


async def _run_single_telegram_bot_async(
    settings: Settings,
    bot_config: BotConfig,
) -> None:
    """
    Run a single Telegram bot asynchronously.

    This is the async wrapper that allows multiple bots to run concurrently.

    Args:
        settings: Application settings
        bot_config: Configuration for this specific bot instance
    """
    bot = TelegramBot(settings, bot_config=bot_config)
    logger.info(f"Starting Telegram bot '{bot_config.id}'...")

    if not bot.telegram_available:
        logger.error(f"Bot '{bot_config.id}': python-telegram-bot not installed")
        return

    token = bot._token
    if not token:
        logger.error(f"Bot '{bot_config.id}': no token configured")
        return

    app = bot.Application.builder().token(token).build()

    # Register all handlers
    app.add_handler(bot.CommandHandler("start", bot._start_command))
    app.add_handler(bot.CommandHandler("reset", bot._reset_command))
    app.add_handler(bot.CommandHandler("help", bot._help_command))
    app.add_handler(bot.CommandHandler("compact", bot._compact_command))
    app.add_handler(bot.CommandHandler("whoami", bot._whoami_command))
    app.add_handler(bot.CommandHandler("agents", bot._agents_command))
    app.add_handler(bot.CommandHandler("agent", bot._agent_command))
    app.add_handler(
        bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, bot._handle_message)
    )

    # Run the bot (this blocks until stopped)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message"])

    # Keep the bot running
    logger.info(f"Bot '{bot_config.id}' is running and listening for messages")

    # Run until the bot is stopped (Ctrl+C)
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info(f"Bot '{bot_config.id}' received shutdown signal")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def run_telegram_bots(
    settings: Settings,
    bot_name: Optional[str] = None,
) -> None:
    """
    Run one or more Telegram bots concurrently.

    Args:
        settings: Application settings
        bot_name: If provided, run only this specific bot by name.
                 If None, run all configured Telegram bots.
    """
    # Configure logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    for noisy_logger in ("httpx", "httpcore", "apscheduler", "telegram.ext"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Get the bot(s) to run
    if bot_name:
        bot_config = settings.bot_registry.get_bot(bot_name)
        if not bot_config:
            logger.error(f"Bot '{bot_name}' not found in bot registry")
            logger.info("Available bots: " + ", ".join(settings.bot_registry.bots.keys()))
            return

        if bot_config.platform != "telegram":
            logger.error(
                f"Bot '{bot_name}' is not a Telegram bot (platform: {bot_config.platform})"
            )
            return

        bots_to_run = [bot_config]
    else:
        bots_to_run = settings.bot_registry.get_telegram_bots()
        if not bots_to_run:
            logger.error("No Telegram bots configured")
            logger.info("Run 'flavia --setup-telegram' to configure a bot")
            return

    logger.info(f"Starting {len(bots_to_run)} Telegram bot(s) concurrently...")
    for bot in bots_to_run:
        logger.info(f"  - {bot.id}: using agent '{bot.default_agent}'")
        if bot.access.allow_all:
            logger.warning(f"    ⚠  Public access (no whitelist)")
        elif bot.access.allowed_users:
            logger.info(f"    🔒 Access restricted to {len(bot.access.allowed_users)} user(s)")
        else:
            logger.warning(f"    ⚠  No explicit whitelist - likely public")

    # Run all bots concurrently using asyncio.gather()
    try:
        asyncio.run(_run_multiple_bots_async(settings, bots_to_run))
    except KeyboardInterrupt:
        logger.info("\nReceived shutdown signal (Ctrl+C)")
    except Exception as e:
        logger.error(f"Error running bots: {e}")
        raise


async def _run_multiple_bots_async(
    settings: Settings,
    bot_configs: list[BotConfig],
) -> None:
    """
    Run multiple Telegram bots concurrently using asyncio.gather().

    Args:
        settings: Application settings
        bot_configs: List of bot configurations to run
    """
    tasks = [_run_single_telegram_bot_async(settings, bot_config) for bot_config in bot_configs]

    # Run all tasks concurrently
    await asyncio.gather(*tasks, return_exceptions=True)
