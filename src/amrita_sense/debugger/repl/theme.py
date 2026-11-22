"""ANSI styling for the rescue REPL.

Only presentation lives here: no command logic, no I/O decisions.  Two rules
matter:

* colour is decided once per session (a redirected stream must not receive
  escape codes), and ``NO_COLOR`` / ``TERM=dumb`` always win;
* prompts given to :func:`input` wrap escapes in ``\\001`` / ``\\002`` so
  readline does not count them when computing the cursor column.  Without that,
  a coloured prompt puts the cursor in the wrong place as soon as you type.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

RESET = "\x1b[0m"

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_PROMPT_START = "\001"
_PROMPT_END = "\002"

#: Restrained palette: one accent, no gradients, no bright white.
PROMPT = "36"
ADDRESS = "36"
ERROR = "31"
WARN = "33"
OK = "32"
DIM = "90"
BOLD = "1"


def sanitize(text: str) -> str:
    """Strip terminal control sequences from workflow-controlled text.

    Node tags and exception messages come from user code; emitting them raw
    lets a workflow move the cursor, recolour the prompt or spoof output while
    an operator is debugging.  Newlines and tabs are kept.
    """
    return _CONTROL.sub("", _ESCAPE.sub("", text))


class Theme:
    """A colour switch plus the two ways of wrapping text."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = bool(enabled)

    def paint(self, text: str, code: str = "") -> str:
        """Colour *text* for ordinary output."""
        if not self.enabled or not code:
            return text
        return f"\x1b[{code}m{text}{RESET}"

    def prompt(self, text: str, code: str = PROMPT) -> str:
        """Colour a readline prompt without corrupting the cursor column."""
        if not self.enabled or not code:
            return text
        return (
            f"{_PROMPT_START}\x1b[{code}m{_PROMPT_END}"
            f"{text}"
            f"{_PROMPT_START}{RESET}{_PROMPT_END}"
        )


def color_enabled(stream: Any = None, *, default: bool = False) -> bool:
    """Decide whether *stream* should receive ANSI escapes.

    ``NO_COLOR`` and ``TERM=dumb`` disable colour unconditionally; ``FORCE_COLOR``
    (or ``CLICOLOR_FORCE``) enables it even when the stream is a pipe.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    for name in ("FORCE_COLOR", "CLICOLOR_FORCE"):
        value = os.environ.get(name)
        if value and value != "0":
            return True
    target = stream if stream is not None else sys.stdout
    try:
        return bool(target.isatty())
    except (AttributeError, OSError, ValueError):
        return default


__all__ = [
    "ADDRESS",
    "BOLD",
    "DIM",
    "ERROR",
    "OK",
    "PROMPT",
    "RESET",
    "WARN",
    "Theme",
    "color_enabled",
    "sanitize",
]
