"""LLM-based summarization for files and directories."""

import logging
from pathlib import Path
from typing import Any, Optional

from .scanner import FileEntry

logger = logging.getLogger(__name__)


SUMMARIZE_FILE_PROMPT = """Summarize the following document in 1-3 concise sentences.
Focus on the main topic, key findings, or purpose of the document.
Respond ONLY with the summary text, nothing else.

Document path: {path}
Document content (first {max_chars} characters):

{content}"""


SUMMARIZE_DIRECTORY_PROMPT = """Based on the following list of files and their summaries, write a 1-2 sentence summary
describing the purpose/contents of this directory.
Respond ONLY with the summary text, nothing else.

Directory: {dir_path}

Files:
{file_list}"""


def summarize_file(
    entry: FileEntry,
    base_dir: Path,
    api_key: str,
    api_base_url: str,
    model: str,
    max_chars: int = 4000,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    connect_timeout: float = 10.0,
) -> Optional[str]:
    """
    Generate a summary for a single file using an LLM.

    Args:
        entry: The FileEntry to summarize.
        base_dir: Project root directory.
        api_key: LLM API key.
        api_base_url: LLM API base URL.
        model: Model ID to use.
        max_chars: Maximum characters of content to send.
        headers: Optional additional HTTP headers.
        timeout: Request timeout in seconds (default: 30.0).
        connect_timeout: Connection timeout in seconds (default: 10.0).

    Returns:
        Summary string, or None on failure.
    """
    # Determine which file to read (converted version or original)
    if entry.converted_to:
        file_path = base_dir / entry.converted_to
    else:
        file_path = base_dir / entry.path

    if not file_path.exists():
        return None

    # Only summarize text-readable files
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None

    if not content.strip():
        return None

    # Truncate content for LLM context
    truncated = content[:max_chars]

    prompt = SUMMARIZE_FILE_PROMPT.format(
        path=entry.path,
        max_chars=max_chars,
        content=truncated,
    )

    return _call_llm(prompt, api_key, api_base_url, model, headers, timeout, connect_timeout)


def summarize_directory(
    dir_path: str,
    file_summaries: list[tuple[str, str]],
    api_key: str,
    api_base_url: str,
    model: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    connect_timeout: float = 10.0,
) -> Optional[str]:
    """
    Generate a summary for a directory based on its files' summaries.

    Args:
        dir_path: Relative directory path.
        file_summaries: List of (filename, summary) tuples.
        api_key: LLM API key.
        api_base_url: LLM API base URL.
        model: Model ID to use.
        headers: Optional additional HTTP headers.
        timeout: Request timeout in seconds (default: 30.0).
        connect_timeout: Connection timeout in seconds (default: 10.0).

    Returns:
        Summary string, or None on failure.
    """
    if not file_summaries:
        return None

    file_list = "\n".join(f"  - {name}: {summary}" for name, summary in file_summaries)

    prompt = SUMMARIZE_DIRECTORY_PROMPT.format(
        dir_path=dir_path,
        file_list=file_list,
    )

    return _call_llm(prompt, api_key, api_base_url, model, headers, timeout, connect_timeout)


def _call_llm(
    prompt: str,
    api_key: str,
    api_base_url: str,
    model: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    connect_timeout: float = 10.0,
) -> Optional[str]:
    """
    Make a simple LLM call and return the response text.

    Args:
        prompt: The prompt to send to the LLM.
        api_key: API key for authentication.
        api_base_url: Base URL for the API.
        model: Model identifier.
        headers: Optional HTTP headers.
        timeout: Request timeout in seconds.
        connect_timeout: Connection timeout in seconds.

    Returns:
        Response text, or None on failure.
    """
    try:
        import httpx
        from openai import OpenAI

        timeout_config = httpx.Timeout(timeout, connect=connect_timeout)
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": api_base_url,
            "timeout": timeout_config,
        }
        if headers:
            client_kwargs["default_headers"] = headers

        try:
            client = OpenAI(**client_kwargs)
        except TypeError as exc:
            # Compatibility fallback for OpenAI SDK/httpx version mismatch.
            # Some versions have incompatible kwargs (e.g., 'proxies' or 'default_headers').
            exc_str = str(exc).lower()
            if "proxies" in exc_str or "default_headers" in exc_str or "timeout" in exc_str:
                logger.debug(f"Using OpenAI SDK compatibility fallback due to: {exc}")
                openai_kwargs = {"api_key": api_key, "base_url": api_base_url}
                client = OpenAI(
                    **openai_kwargs,
                    http_client=httpx.Client(
                        timeout=timeout_config,
                        headers=headers if headers else None,
                    ),
                )
            else:
                raise

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()

        logger.warning(f"LLM returned empty response for model {model}")
        return None

    except ImportError as e:
        logger.error(f"Required library not available: {e}")
        return None
    except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
        logger.warning(f"LLM request timeout for model {model}: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"LLM HTTP error for model {model}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling LLM model {model}: {e}", exc_info=True)
        return None
