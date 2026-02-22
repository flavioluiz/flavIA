### Task 3.4 -- Abstract Messaging Interface ✅

**Difficulty**: Hard | **Dependencies**: Tasks 3.1, 3.2 | **Status**: Done

Extract a shared `BaseMessagingBot` abstraction from `TelegramBot` to centralize cross-platform bot behavior and prepare future platforms.

**Implementation Summary**:

- Added `interfaces/base_bot.py` with:
  - `BaseMessagingBot` abstract base class
  - shared auth/access checks
  - shared per-user agent lifecycle (`get/create/reset/switch`)
  - shared text chunking by platform limit
  - shared command metadata and help rendering
  - structured response/action wrappers (`BotResponse`, `SendFileAction`)
- Refactored `interfaces/telegram_interface.py`:
  - `TelegramBot` now extends `BaseMessagingBot`
  - message flow uses shared processing (`_handle_message_common`)
  - Telegram-specific commands and API handlers remain in subclass
  - keeps Telegram footer/compaction warning behavior

**Key files modified/created**:

- `interfaces/base_bot.py` (new)
- `interfaces/telegram_interface.py` (refactor to subclass base)
- `interfaces/__init__.py` (exports base abstractions)

**Behavior/compatibility notes**:

- Legacy Telegram entrypoint `run_telegram_bot()` remains available.
- Existing Telegram commands remain supported (`/start`, `/help`, `/whoami`, `/reset`, `/compact`, `/agents`, `/agent`).
- Multi-bot runner from Task 3.3 continues unchanged in public API.

**Testing**:

- Telegram regression suite remains green after refactor:
  - access control
  - agent command switching
  - compact command behavior
  - message resilience paths
  - multi-bot runner compatibility

**New dependencies**: None
