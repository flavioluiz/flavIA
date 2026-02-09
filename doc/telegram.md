# Telegram

Turn your assistant into a Telegram bot accessible from anywhere.

## Quick setup

```bash
flavia --setup-telegram
```

The wizard guides you through:

1. **Getting a token from @BotFather**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow the prompts
   - Copy the token (format: `123456789:ABCdefGHI...`)

2. **Configuring access control**
   - **Restricted** (recommended): only specific user IDs can use the bot
   - **Public**: anyone who finds your bot can use it (uses your API credits!)

3. **Finding your user ID**
   - Search for `@userinfobot` on Telegram
   - Send any message to get your ID

## Manual configuration

In `.flavia/.env`:

```bash
# Bot token (required)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...

# Option 1: restrict to specific users (recommended)
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Option 2: allow anyone (use with caution)
TELEGRAM_ALLOW_ALL_USERS=true
```

## Starting the bot

```bash
flavia --telegram
```

If the bot is not yet configured, the wizard is offered automatically when running in an interactive terminal.

## How it works

- Each Telegram user gets their own agent instance with an independent conversation
- Access control is verified by user ID
- The bot uses the same agent configuration (`.flavia/agents.yaml`) and providers from the folder where it was started
- The session persists as long as the process is running

## Dependency installation

The Telegram interface requires the `python-telegram-bot` package:

```bash
.venv/bin/pip install python-telegram-bot==22.6
```

Or via extras:

```bash
.venv/bin/pip install -e ".[telegram]"
```
