"""LLM-based summarization for files and directories."""

import logging
import re
from pathlib import Path
from typing import Any, Optional

from .scanner import FileEntry

logger = logging.getLogger(__name__)
_LAST_LLM_CALL_INFO: dict[str, Any] = {}


def get_last_llm_call_info() -> dict[str, Any]:
    """Return metadata from the most recent LLM summarization call."""
    return dict(_LAST_LLM_CALL_INFO)


def _set_last_llm_call_info(**kwargs: Any) -> None:
    """Store metadata for the most recent LLM summarization call."""
    _LAST_LLM_CALL_INFO.clear()
    _LAST_LLM_CALL_INFO.update(kwargs)


SUMMARIZE_FILE_PROMPT = """Summarize the following document in 1-3 concise sentences.
Focus on the main topic, key findings, or purpose of the document.
Respond ONLY with the summary text, nothing else.

Document path: {path}
Document content (first {max_chars} characters):

{content}"""


SUMMARIZE_FILE_WITH_QUALITY_PROMPT = """Summarize the following document and assess text extraction quality.

Respond with EXACTLY two lines:
Line 1: A 1-3 sentence summary of the main topic, key findings, or purpose.
Line 2: One of these words only: good / partial / poor
  - good: text is clean, readable, and complete
  - partial: equations/tables mangled, occasional garbled characters, or truncated content
  - poor: mostly unreadable, empty, or appears to be a scanned image without proper OCR

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
    relative_path = Path(entry.converted_to) if entry.converted_to else Path(entry.path)
    file_path = (base_dir / relative_path).resolve()
    base_dir_resolved = base_dir.resolve()

    # Prevent reading files outside project directory from manipulated catalog paths.
    try:
        file_path.relative_to(base_dir_resolved)
    except ValueError:
        logger.warning(f"Skipping summary for path outside base_dir: {relative_path}")
        return None

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


def summarize_file_with_quality(
    entry: FileEntry,
    base_dir: Path,
    api_key: str,
    api_base_url: str,
    model: str,
    max_chars: int = 4000,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    connect_timeout: float = 10.0,
) -> tuple[Optional[str], Optional[str]]:
    """
    Generate a summary and extraction quality assessment for a single file.

    Returns:
        Tuple of (summary, quality) where quality is "good", "partial", "poor", or None.
    """
    relative_path = Path(entry.converted_to) if entry.converted_to else Path(entry.path)
    file_path = (base_dir / relative_path).resolve()
    base_dir_resolved = base_dir.resolve()

    try:
        file_path.relative_to(base_dir_resolved)
    except ValueError:
        logger.warning(f"Skipping summary for path outside base_dir: {relative_path}")
        return None, None

    if not file_path.exists():
        return None, None

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None, None

    if not content.strip():
        return None, None

    truncated = content[:max_chars]

    prompt = SUMMARIZE_FILE_WITH_QUALITY_PROMPT.format(
        path=entry.path,
        max_chars=max_chars,
        content=truncated,
    )

    raw = _call_llm(prompt, api_key, api_base_url, model, headers, timeout, connect_timeout)
    if not raw:
        return None, None

    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return None, None

    quality: Optional[str] = None
    quality_index: Optional[int] = None
    for i in range(len(lines) - 1, -1, -1):
        m = re.fullmatch(
            r"(?:quality\s*[:=-]\s*)?(good|partial|poor)\.?",
            lines[i],
            flags=re.IGNORECASE,
        )
        if m:
            quality = m.group(1).lower()
            quality_index = i
            break

    summary_lines = (
        [line for idx, line in enumerate(lines) if idx != quality_index]
        if quality_index is not None
        else lines
    )
    summary = " ".join(summary_lines).strip() or None
    return summary, quality


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
    def _extract_response_text(response: Any) -> Optional[str]:
        """Extract text from chat completion response across provider variants."""
        choices = getattr(response, "choices", None)
        if not choices:
            return None

        message = getattr(choices[0], "message", None)
        if message is None:
            return None

        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                else:
                    text = getattr(item, "text", None) or getattr(item, "content", None)
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                return "\n".join(parts).strip()

        # Some providers expose auxiliary text fields.
        for attr in ("output_text", "text"):
            value = getattr(message, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    _set_last_llm_call_info(status="started", model=model)

    try:
        import httpx
        import openai as openai_module
        from openai import OpenAI

        api_connection_error = getattr(openai_module, "APIConnectionError", None)
        api_timeout_error = getattr(openai_module, "APITimeoutError", None)
        api_status_error = getattr(openai_module, "APIStatusError", None)
        timeout_error_types = tuple(
            err for err in (api_timeout_error, api_connection_error) if isinstance(err, type)
        )

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

        def _create_completion(request_prompt: str, max_tokens: int, temperature: float) -> Any:
            try:
                return client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": request_prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as e:
                if timeout_error_types and isinstance(e, timeout_error_types):
                    logger.warning(f"LLM OpenAI timeout/connection error for model {model}: {e}")
                    _set_last_llm_call_info(
                        status="timeout_or_connection_error",
                        model=model,
                        error=str(e),
                    )
                    return None
                if isinstance(api_status_error, type) and isinstance(e, api_status_error):
                    status_code = getattr(e, "status_code", "unknown")
                    logger.warning(f"LLM OpenAI API error for model {model}: status={status_code}")
                    _set_last_llm_call_info(
                        status="api_status_error",
                        model=model,
                        api_status=status_code,
                    )
                    return None
                raise

        response = _create_completion(prompt, max_tokens=200, temperature=0.3)
        if response is None:
            return None

        text = _extract_response_text(response)
        if text:
            _set_last_llm_call_info(status="ok", model=model, retried=False)
            return text

        finish_reason = None
        usage = getattr(response, "usage", None)
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        choices = getattr(response, "choices", None)
        if choices:
            finish_reason = getattr(choices[0], "finish_reason", None)

        logger.warning(
            f"LLM returned empty response for model {model} "
            f"(finish_reason={finish_reason}, completion_tokens={completion_tokens}). "
            "Retrying once with stricter no-reasoning instruction."
        )

        retry_prompt = (
            prompt
            + "\n\nIMPORTANT: Return ONLY the final answer text. "
            "Do not include reasoning/thinking."
        )
        retry_response = _create_completion(retry_prompt, max_tokens=800, temperature=0.0)
        if retry_response is None:
            return None

        retry_text = _extract_response_text(retry_response)
        if retry_text:
            _set_last_llm_call_info(
                status="ok",
                model=model,
                retried=True,
                first_finish_reason=finish_reason,
                first_completion_tokens=completion_tokens,
            )
            return retry_text

        retry_finish = None
        retry_usage = getattr(retry_response, "usage", None)
        retry_tokens = getattr(retry_usage, "completion_tokens", None) if retry_usage else None
        retry_choices = getattr(retry_response, "choices", None)
        if retry_choices:
            retry_finish = getattr(retry_choices[0], "finish_reason", None)

        logger.warning(
            f"LLM returned empty response for model {model} after retry "
            f"(finish_reason={retry_finish}, completion_tokens={retry_tokens})"
        )
        _set_last_llm_call_info(
            status="empty_after_retry",
            model=model,
            first_finish_reason=finish_reason,
            first_completion_tokens=completion_tokens,
            retry_finish_reason=retry_finish,
            retry_completion_tokens=retry_tokens,
        )
        return None

    except ImportError as e:
        logger.error(f"Required library not available: {e}")
        _set_last_llm_call_info(status="import_error", model=model, error=str(e))
        return None
    except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
        logger.warning(f"LLM request timeout for model {model}: {e}")
        _set_last_llm_call_info(status="httpx_timeout", model=model, error=str(e))
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"LLM HTTP error for model {model}: {e.response.status_code}")
        _set_last_llm_call_info(
            status="httpx_status_error",
            model=model,
            api_status=getattr(e.response, "status_code", "unknown"),
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling LLM model {model}: {e}", exc_info=True)
        _set_last_llm_call_info(status="unexpected_error", model=model, error=str(e))
        return None
