"""LLM-based summarization for files and directories."""

from pathlib import Path
from typing import Optional, Any

from .scanner import FileEntry


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

    return _call_llm(prompt, api_key, api_base_url, model, headers)


def summarize_directory(
    dir_path: str,
    file_summaries: list[tuple[str, str]],
    api_key: str,
    api_base_url: str,
    model: str,
    headers: Optional[dict[str, str]] = None,
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

    return _call_llm(prompt, api_key, api_base_url, model, headers)


def _call_llm(
    prompt: str,
    api_key: str,
    api_base_url: str,
    model: str,
    headers: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Make a simple LLM call and return the response text."""
    try:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": api_base_url,
        }
        if headers:
            client_kwargs["default_headers"] = headers

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )

        if response.choices:
            return response.choices[0].message.content.strip()
        return None

    except Exception:
        return None
