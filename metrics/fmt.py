"""Number and word formatting shared by the card and its notes."""

from __future__ import annotations


def compact(n: int) -> str:
    """1,284 / 12.9K / 4.2M"""
    if n < 10_000:
        return f"{n:,}"
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div * 0.99995:
            v = n / div
            text = f"{v:.1f}" if v < 100 else f"{v:.0f}"
            return text.removesuffix(".0") + suffix
    return f"{n:,}"


def plural(n: int, word: str) -> str:
    return f"{word}{'' if n == 1 else 's'}"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def hour(h: int) -> str:
    return {0: "midnight", 12: "noon"}.get(h) or f"{h % 12} {'am' if h < 12 else 'pm'}"
