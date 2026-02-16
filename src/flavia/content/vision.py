"""Vision-capable LLM utilities for image analysis.

Provides multimodal API calls for analyzing images using vision-capable models.
"""

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default prompt for image analysis
DEFAULT_IMAGE_ANALYSIS_PROMPT = """Describe this image in detail.
Include the following aspects if applicable:
- Main subject or content
- Colors, shapes, and composition
- Any visible text or numbers
- Context or setting
- Technical details (for diagrams, charts, screenshots, etc.)

Respond with a clear, informative description."""


def encode_image_base64(image_path: Path) -> tuple[str, str]:
    """
    Encode an image file to base64 and determine its MIME type.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (base64_encoded_data, mime_type).

    Raises:
        FileNotFoundError: If the image file doesn't exist.
        ValueError: If the file is empty or MIME type cannot be determined.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Determine MIME type
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        # Fallback based on extension
        ext_to_mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".svg": "image/svg+xml",
        }
        mime_type = ext_to_mime.get(image_path.suffix.lower())

    if not mime_type:
        raise ValueError(f"Cannot determine MIME type for: {image_path}")

    # Read and encode
    with open(image_path, "rb") as f:
        image_data = f.read()

    if not image_data:
        raise ValueError(f"Image file is empty: {image_path}")

    encoded = base64.b64encode(image_data).decode("utf-8")
    return encoded, mime_type


def convert_svg_to_png(svg_path: Path) -> Optional[bytes]:
    """
    Convert an SVG file to PNG format using cairosvg.

    Args:
        svg_path: Path to the SVG file.

    Returns:
        PNG image data as bytes, or None if conversion fails.
    """
    try:
        import cairosvg

        png_data = cairosvg.svg2png(url=str(svg_path))
        return png_data
    except ImportError:
        logger.debug("cairosvg not available for SVG conversion")
        return None
    except Exception as e:
        logger.warning(f"SVG to PNG conversion failed: {e}")
        return None


def _prepare_image_content(
    image_path: Path,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Prepare image content for API call.

    Handles SVG conversion if cairosvg is available.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (base64_data, mime_type, error).
        If successful, error is None. If failed, data and mime_type are None.
    """
    # Handle SVG specially
    if image_path.suffix.lower() == ".svg":
        png_data = convert_svg_to_png(image_path)
        if png_data:
            encoded = base64.b64encode(png_data).decode("utf-8")
            return encoded, "image/png", None
        else:
            # Fall back to reading SVG as text for models that might handle it
            # or return an error suggesting cairosvg installation
            logger.info(
                f"SVG conversion unavailable for {image_path}, "
                "attempting direct SVG analysis"
            )
            try:
                encoded, mime_type = encode_image_base64(image_path)
                return encoded, mime_type, None
            except Exception as e:
                return None, None, f"Failed to encode SVG: {e}"

    try:
        encoded, mime_type = encode_image_base64(image_path)
        return encoded, mime_type, None
    except Exception as e:
        return None, None, str(e)


def analyze_image(
    image_path: Path,
    api_key: str,
    api_base_url: str,
    model: str,
    prompt: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 60.0,
    connect_timeout: float = 10.0,
    max_tokens: int = 1000,
    max_image_bytes: int = 20 * 1024 * 1024,
) -> tuple[Optional[str], Optional[str]]:
    """
    Analyze an image using a vision-capable LLM model.

    Args:
        image_path: Path to the image file.
        api_key: API key for authentication.
        api_base_url: Base URL for the API.
        model: Model identifier (must be vision-capable).
        prompt: Custom analysis prompt. Uses default if None.
        headers: Optional HTTP headers.
        timeout: Request timeout in seconds.
        connect_timeout: Connection timeout in seconds.
        max_tokens: Maximum tokens in the response.
        max_image_bytes: Maximum allowed image file size in bytes.

    Returns:
        Tuple of (description, error).
        On success: (description_text, None)
        On failure: (None, error_message)
    """
    # Guardrail: prevent very large image payloads/cost spikes.
    try:
        file_size = image_path.stat().st_size
    except OSError as e:
        return None, f"Failed to read image metadata: {e}"

    if file_size == 0:
        return None, f"Image file is empty: {image_path}"

    if max_image_bytes > 0 and file_size > max_image_bytes:
        return (
            None,
            f"Image file too large ({file_size} bytes). "
            f"Maximum supported size is {max_image_bytes} bytes.",
        )

    # Prepare image content
    base64_data, mime_type, prep_error = _prepare_image_content(image_path)
    if prep_error:
        return None, prep_error

    # Build the multimodal message
    analysis_prompt = prompt or DEFAULT_IMAGE_ANALYSIS_PROMPT
    image_url = f"data:{mime_type};base64,{base64_data}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": analysis_prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]

    return _call_vision_llm(
        messages=messages,
        api_key=api_key,
        api_base_url=api_base_url,
        model=model,
        headers=headers,
        timeout=timeout,
        connect_timeout=connect_timeout,
        max_tokens=max_tokens,
    )


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

    # Some providers expose auxiliary text fields
    for attr in ("output_text", "text"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _is_vision_incompatible_error(error: Exception) -> bool:
    """Check if the error indicates the model doesn't support vision."""
    error_str = str(error).lower()

    # Strong signals that explicitly refer to image/vision capability.
    explicit_indicators = [
        "does not support vision",
        "vision not supported",
        "vision capability missing",
        "image analysis not available",
        "does not support image",
        "not support images",
        "multimodal not supported",
        "image input is not supported",
        "image_url is not supported",
    ]
    if any(indicator in error_str for indicator in explicit_indicators):
        return True

    # Mixed signals: only treat content-type/support errors as vision incompatibility
    # when the message also mentions image/vision specific fields.
    has_image_context = any(
        marker in error_str
        for marker in ("image_url", "image input", "vision", "multimodal")
    )
    has_support_error = any(
        marker in error_str
        for marker in ("unsupported", "does not support", "not support", "content type")
    )
    return has_image_context and has_support_error


def _call_vision_llm(
    messages: list[dict],
    api_key: str,
    api_base_url: str,
    model: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 60.0,
    connect_timeout: float = 10.0,
    max_tokens: int = 1000,
) -> tuple[Optional[str], Optional[str]]:
    """
    Make a vision LLM call with multimodal messages.

    Args:
        messages: The messages list with text and image content.
        api_key: API key for authentication.
        api_base_url: Base URL for the API.
        model: Model identifier.
        headers: Optional HTTP headers.
        timeout: Request timeout in seconds.
        connect_timeout: Connection timeout in seconds.
        max_tokens: Maximum tokens in the response.

    Returns:
        Tuple of (response_text, error).
    """
    try:
        import httpx
        import openai as openai_module
        from openai import OpenAI

        api_connection_error = getattr(openai_module, "APIConnectionError", None)
        api_timeout_error = getattr(openai_module, "APITimeoutError", None)
        api_status_error = getattr(openai_module, "APIStatusError", None)

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
            # Compatibility fallback for OpenAI SDK/httpx version mismatch
            exc_str = str(exc).lower()
            if "proxies" in exc_str or "default_headers" in exc_str or "timeout" in exc_str:
                logger.debug(f"Using OpenAI SDK compatibility fallback due to: {exc}")
                client = OpenAI(
                    api_key=api_key,
                    base_url=api_base_url,
                    http_client=httpx.Client(
                        timeout=timeout_config,
                        headers=headers if headers else None,
                    ),
                )
            else:
                raise

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
            )
        except Exception as e:
            # Check for vision-incompatible model error
            if _is_vision_incompatible_error(e):
                return None, (
                    f"Model '{model}' does not appear to support vision/image analysis. "
                    "Please use a vision-capable model like 'synthetic:hf:moonshotai/Kimi-K2.5'. "
                    f"Provider error: {e}"
                )

            # Handle timeout/connection errors
            timeout_error_types = tuple(
                err
                for err in (api_timeout_error, api_connection_error)
                if isinstance(err, type)
            )
            if timeout_error_types and isinstance(e, timeout_error_types):
                return None, f"Connection timeout or error: {e}"

            # Handle API status errors
            if isinstance(api_status_error, type) and isinstance(e, api_status_error):
                status_code = getattr(e, "status_code", "unknown")
                error_body = getattr(e, "body", str(e))
                if _is_vision_incompatible_error(e) or _is_vision_incompatible_error(
                    Exception(str(error_body))
                ):
                    return None, (
                        f"Model '{model}' does not appear to support vision/image analysis. "
                        f"Please use a vision-capable model. Provider error: {error_body}"
                    )
                return None, f"API error (status {status_code}): {error_body}"

            return None, f"LLM API error: {e}"

        text = _extract_response_text(response)
        if text:
            return text, None

        # Empty response
        finish_reason = None
        choices = getattr(response, "choices", None)
        if choices:
            finish_reason = getattr(choices[0], "finish_reason", None)

        return None, f"Model returned empty response (finish_reason={finish_reason})"

    except ImportError as e:
        return None, f"Required library not available: {e}"
    except Exception as e:
        logger.error(f"Unexpected error in vision LLM call: {e}", exc_info=True)
        return None, f"Unexpected error: {e}"
