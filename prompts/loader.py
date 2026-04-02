"""
CoderX — Prompt Loader
Loads prompt templates from the prompts/ directory and renders them
with runtime variables via str.format_map().
"""
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, **variables: Any) -> str:
    """
    Load a prompt template by filename (without .md extension)
    and render it with the provided variables.

    Args:
        name: Filename without extension, e.g. "agent_reason"
        **variables: Key-value pairs to substitute into the template.

    Returns:
        Rendered prompt string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    template = path.read_text(encoding="utf-8")

    # Strip comment lines (lines starting with #) that are loader directives
    lines = template.splitlines()
    content_lines = [
        line for line in lines
        if not line.startswith("# CoderX") and not line.startswith("# Variables") and not line.startswith("# Used by")
    ]
    template = "\n".join(content_lines).strip()

    if not variables:
        return template

    # Use format_map with a safe fallback — unknown keys are left as-is
    return template.format_map(_SafeFormatMap(variables))


class _SafeFormatMap(dict):
    """
    A dict subclass that returns the original placeholder string
    for any missing key, instead of raising KeyError.
    This prevents partially-rendered prompts from crashing.
    """
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"
