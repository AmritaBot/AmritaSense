"""Minimal line tokenizer for the SenseDBG rescue REPL.

The grammar is deliberately tiny: whitespace-separated words, optional
quotes, and ``#`` to end-of-line.  It is *not* a Python tokenizer, and it
must never grow into one — arbitrary Python goes through ``py``, which
hands the line to a real interpreter console.
"""

from __future__ import annotations

_QUOTES = ("'", '"')
_WHITESPACE = " \t\r\n\u3000\ufeff"

#: Input-method friendly folding: full-width punctuation maps to ASCII so a
#: CJK IME cannot silently produce a command that "looks" right but is not.
_FOLD = str.maketrans(
    {
        "\u3000": " ",
        "，": ",",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "＝": "=",
        "＋": "+",
        "－": "-",
        "＊": "*",
        "＃": "#",
    }
)


def fold(line: str) -> str:
    """Normalize full-width punctuation and strip the line terminator."""
    return line.translate(_FOLD).rstrip("\r\n")


def lex(line: str) -> list[str]:
    """Split *line* into tokens.

    Args:
        line: A raw input line (terminator optional).

    Returns:
        The token list.  Empty when the line is blank or only a comment.
    """
    source = fold(line)
    tokens: list[str] = []
    buf: list[str] = []
    index = 0
    size = len(source)
    while index < size:
        char = source[index]
        if char in _WHITESPACE:
            if buf:
                tokens.append("".join(buf))
                buf.clear()
            index += 1
            continue
        if char == "#":
            break
        if char in _QUOTES:
            # Quotes group and are kept, so `py print('a b')` round-trips to Python.
            buf.append(char)
            index += 1
            while index < size and source[index] != char:
                buf.append(source[index])
                index += 1
            if index < size:
                buf.append(char)
            index += 1
            continue
        buf.append(char)
        index += 1
    if buf:
        tokens.append("".join(buf))
    return tokens


__all__ = ["fold", "lex"]
