"""Bot runner utilities for managing multiple concurrent bot instances."""

import asyncio
import logging
from contextlib import suppress
from typing import Optional

from flavia.config import Settings
from flavia.config.bots import BotConfig

from .telegram_interface import TelegramBot

logger = logging.getLogger(__name__)


def _iter_exception_chain(exc: BaseException):
    """Yield exception and chained causes/contexts (without cycles)."""
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _format_exception_chain(exc: BaseException) -> str:
    """Format chained exceptions for concise diagnostics."""
    parts: list[str] = []
    for item in _iter_exception_chain(exc):
        msg = str(item).strip()
        if msg:
            parts.append(f"{item.__class__.__name__}: {msg}")
        else:
            parts.append(item.__class__.__name__)
    return " <- ".join(parts)


def _is_connect_error(exc: BaseException) -> bool:
    """Return True when the exception chain looks like a network connect failure."""
    for item in _iter_exception_chain(exc):
        name = item.__class__.__name__.lower()
        if "connecterror" in name:
            return True
        if isinstance(item, OSError) and getattr(item, "errno", None) in {8, 101, 110, 111, 113}:
            return True
    return False


def _build_telegram_application(bot: TelegramBot, token: str):
    """Build Telegram application and register handlers with isolated httpx client."""
    # Create isolated httpx client for this bot instance to avoid connection pool sharing
    # when running multiple bots concurrently
    from telegram.request import HTTPXRequest

    # Create separate HTTPXRequest instance with its own connection pool
    httpx_request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=5.0,
    )

    builder = bot.Application.builder().token(token).request(httpx_request)

    app = builder.build()

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
    app.add_error_handler(bot._error_handler)
    return app


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

    app = None

    # Retry initialize for transient connectivity failures (DNS/TLS handshake hiccups).
    max_attempts = 3
    retry_delay_s = 1.0
    for attempt in range(1, max_attempts + 1):
        app = _build_telegram_application(bot, token)
        try:
            await app.initialize()
            break
        except Exception as exc:
            details = _format_exception_chain(exc)
            if attempt < max_attempts and _is_connect_error(exc):
                logger.warning(
                    "Bot '%s': initialize failed (%d/%d): %s. Retrying in %.1fs...",
                    bot_config.id,
                    attempt,
                    max_attempts,
                    details,
                    retry_delay_s,
                )
                with suppress(Exception):
                    await app.shutdown()
                await asyncio.sleep(retry_delay_s)
                continue
            logger.error("Bot '%s': initialize failed: %s", bot_config.id, details)
            raise

    # Run the bot (this blocks until stopped)
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
        if app is not None:
            with suppress(Exception):
                await app.updater.stop()
            with suppress(Exception):
                await app.stop()
            with suppress(Exception):
                await app.shutdown()


def run_telegram_bots(
    settings: Settings,
    bot_name: Optional[str] = None,
) -> bool:
    """
    Run one or more Telegram bots concurrently.

    Args:
        settings: Application settings
        bot_name: If provided, run only this specific bot by name.
                 If None, run all configured Telegram bots.

    Returns:
        True when bot runtime was started successfully.
        False when configuration/selection errors prevent startup.
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
            return False

        if bot_config.platform != "telegram":
            logger.error(
                f"Bot '{bot_name}' is not a Telegram bot (platform: {bot_config.platform})"
            )
            return False

        bots_to_run = [bot_config]
    else:
        bots_to_run = settings.bot_registry.get_telegram_bots()
        if not bots_to_run:
            logger.error("No Telegram bots configured")
            logger.info("Run 'flavia --setup-telegram' to configure a bot")
            return False

    logger.info(f"Starting {len(bots_to_run)} Telegram bot(s) concurrently...")
    for bot in bots_to_run:
        logger.info(f"  - {bot.id}: using agent '{bot.default_agent}'")
        if bot.access.allow_all:
            logger.warning("    ⚠  Public access (no whitelist)")
        elif bot.access.allowed_users:
            logger.info(f"    🔒 Access restricted to {len(bot.access.allowed_users)} user(s)")
        else:
            logger.warning("    ⚠  No explicit whitelist - likely public")

    # Run all bots concurrently using asyncio.gather()
    try:
        asyncio.run(_run_multiple_bots_async(settings, bots_to_run))
        return True
    except KeyboardInterrupt:
        logger.info("\nReceived shutdown signal (Ctrl+C)")
        return True
    except Exception as e:
        logger.error("Error running bots: %s", _format_exception_chain(e))
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
    await asyncio.gather(*tasks)
