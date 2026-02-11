# Area 7: External Service Integration

Extend flavIA's capabilities beyond the local filesystem by integrating with external services commonly used in academic and professional workflows. A new `.flavia/services.yaml` configuration file manages credentials and settings for all external services, using the same `${ENV_VAR}` expansion mechanism as `providers.yaml`.

```yaml
# .flavia/services.yaml
services:
  email:
    imap_server: "imap.gmail.com"
    imap_port: 993
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "${EMAIL_USERNAME}"
    password: "${EMAIL_APP_PASSWORD}"

  google_calendar:
    credentials_file: "google_credentials.json"
    calendar_id: "primary"
```

The general principle for all external service tools: **read operations are autonomous** (the agent can search, list, and read without user intervention), while **write operations require user confirmation** (sending emails, creating events, etc.).

---

### Task 7.1 -- Email Integration (IMAP/SMTP)

**Difficulty**: Hard | **Dependencies**: None

Create `tools/services/email.py` with tools for email access via standard IMAP/SMTP protocols.

**Read tools (autonomous, no confirmation required)**:

| Tool | Description |
|------|-------------|
| `search_email` | Search inbox by sender, subject, date range, keywords |
| `read_email` | Read a specific email by ID, including text content and attachment list |
| `list_email_folders` | List available email folders/labels |

**Write tools (require user confirmation before acting)**:

| Tool | Description |
|------|-------------|
| `send_email` | Compose and send an email -- shows full draft to user, waits for approval |
| `reply_email` | Reply to a specific email -- shows draft, waits for approval |

Implementation uses Python's built-in `imaplib` for reading and `smtplib` for sending. No external dependencies required.

For Gmail specifically: requires an App Password (not the regular account password) with 2FA enabled. The setup wizard should guide users through generating an App Password. OAuth2 support could be added later for a smoother experience but is not required for the initial implementation.

The confirmation mechanism for `send_email`/`reply_email` is platform-aware (same infrastructure as Task 6.2):
- CLI: interactive prompt showing the draft and asking `Send this email? [y/N]`
- Telegram/WhatsApp: send the draft as a message, wait for user reply
- Web API: return draft in response, require separate confirmation call

**Key files to modify/create**:
- `tools/services/email.py` (new)
- `tools/services/__init__.py` (new)
- `config/settings.py` (load services config from `services.yaml`)
- `config/loader.py` (discover `services.yaml` in config paths)
- `setup/services_wizard.py` (new -- guided email setup)

**New dependencies**: None (uses Python stdlib `imaplib`, `smtplib`, `email`).

---

### Task 7.2 -- Google Calendar Integration

**Difficulty**: Hard | **Dependencies**: None

Create `tools/services/calendar.py` with Google Calendar tools.

**Read tools (autonomous)**:

| Tool | Description |
|------|-------------|
| `list_events` | List calendar events in a date range |
| `search_events` | Search events by keyword or attendee |
| `get_event` | Get full details of a specific event |

**Write tools (require user confirmation)**:

| Tool | Description |
|------|-------------|
| `create_event` | Create a calendar event -- shows details, waits for approval |
| `update_event` | Modify an existing event -- shows changes, waits for approval |
| `delete_event` | Delete an event -- requires confirmation |

Use `google-api-python-client` + `google-auth-oauthlib` for OAuth2 authentication. First-time setup requires a browser-based OAuth flow; credentials are cached in `.flavia/google_credentials.json` (excluded from git via `.flavia/.gitignore`).

A setup wizard (`--setup-calendar` or part of a broader `--setup-services`) would guide the user through:
1. Creating a Google Cloud project and enabling the Calendar API
2. Downloading OAuth client credentials (`client_secret.json`)
3. Running the OAuth consent flow to authorize access
4. Storing the refresh token securely in `.flavia/`

Configuration in `.flavia/services.yaml`:
```yaml
services:
  google_calendar:
    credentials_file: "google_credentials.json"
    calendar_id: "primary"           # or a specific calendar ID
    default_timezone: "America/Sao_Paulo"
```

**Key files to modify/create**:
- `tools/services/calendar.py` (new)
- `tools/services/__init__.py` (update)
- `setup/calendar_wizard.py` (new -- OAuth flow guide)
- `config/settings.py` (load services config)

**New dependencies** (optional extras): `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`.

---

**[← Back to Roadmap](../roadmap.md)**
