"""Text normalization helpers for user-visible and model-visible output."""

import re


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi_escape_codes(text: str | None) -> str:
    """Remove terminal ANSI color/style codes without changing whitespace."""
    if not text:
        return ""
    return ANSI_ESCAPE_RE.sub("", str(text))
