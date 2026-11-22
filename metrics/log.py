"""Logging that is safe for public Actions logs: emails and private repos are masked."""

from __future__ import annotations

import os

_IN_ACTIONS = bool(os.environ.get("GITHUB_ACTIONS"))


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"::warning::{msg}" if _IN_ACTIONS else f"warning: {msg}", flush=True)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:3]}***@{domain}"


def repo_label(name: str, private: bool, show_private: bool = False) -> str:
    return name if show_private or not private else "<private repo>"
