### Task 3.3 -- Multi-Bot Support ✅

**Difficulty**: Medium | **Dependencies**: Tasks 3.1, 3.2 | **Status**: Done

Allow multiple bot instances to run simultaneously from the same `.flavia/` directory. Each entry in `bots.yaml` maps to a separate bot instance.

**Implementation Summary**:

Created `interfaces/bot_runner.py` module with:
- Async wrapper for running individual Telegram bots
- `run_telegram_bots()` function that uses `asyncio.gather()` to run multiple bots concurrently
- Support for running all bots or a specific bot by name

**CLI Usage**:
- `flavia --telegram` - Run all configured Telegram bots
- `flavia --telegram research-bot` - Run only the "research-bot" instance
- Each bot runs in its own async task, listening independently for messages

**Example `bots.yaml` for multiple bots**:
```yaml
bots:
  research-bot:
    platform: telegram
    token: "${RESEARCH_BOT_TOKEN}"
    default_agent: researcher
    allowed_agents: [researcher, summarizer]
    access:
      allowed_users: [111111111]
      allow_all: false

  study-bot:
    platform: telegram
    token: "${STUDY_BOT_TOKEN}"
    default_agent: summarizer
    allowed_agents: all
    access:
      allowed_users: [222222222, 333333333]
      allow_all: false
```

**Key files modified/created**:
- `interfaces/bot_runner.py` (new) - async bot runner utilities
- `cli.py` - updated `--telegram` argument to accept optional bot name
- `interfaces/__init__.py` - export `run_telegram_bots()`

**Technical Details**:
- Each bot instance creates its own `TelegramBot` object with independent:
  - Bot token
  - Agent configuration (default_agent, allowed_agents)
  - User access control list
  - Per-user agent switch state
- Bots share the same `Settings` object (providers, models, agents.yaml)
- asyncio.gather() manages concurrent execution
- Graceful shutdown on Ctrl+C stops all bots

**Testing**:
- Multiple bots can be started simultaneously
- Each bot responds independently to messages
- Bot-specific access control is enforced per bot
- Graceful shutdown stops all running bots
- Added 5 tests in `test_bot_runner.py`

**New dependencies**: None (uses existing python-telegram-bot)
