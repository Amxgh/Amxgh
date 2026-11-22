from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    timezone: str = "UTC"
    location: tuple[float, float] | None = None  # (latitude, longitude), for sunset
    output_dir: str = "assets"
    cache_dir: str = ".cache/repos"
    show_private_names: bool = False
    include_repos: list[str] = field(default_factory=list)
    exclude_repos: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    max_file_lines: int = 5000
    max_commit_lines: int = 15000
    exclude_dirs: list[str] = field(default_factory=list)
    exclude_files: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    exclude_commits: list[str] = field(default_factory=list)
    top_repos: int = 5
    top_languages: int = 6

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
        get = lambda section, key, default: raw.get(section, {}).get(key, default)  # noqa: E731
        d = cls()
        return cls(
            timezone=get("profile", "timezone", d.timezone),
            location=tuple(get("profile", "location", ())) or None,
            output_dir=get("profile", "output_dir", d.output_dir),
            cache_dir=get("profile", "cache_dir", d.cache_dir),
            show_private_names=get("privacy", "show_private_repo_names", d.show_private_names),
            include_repos=[r.lower() for r in get("repos", "include", [])],
            exclude_repos=[r.lower() for r in get("repos", "exclude", [])],
            emails=[e.lower() for e in get("authorship", "emails", [])],
            max_file_lines=get("lines", "max_file_lines", d.max_file_lines),
            max_commit_lines=get("lines", "max_commit_lines", d.max_commit_lines),
            exclude_dirs=get("lines", "exclude_dirs", []),
            exclude_files=get("lines", "exclude_files", []),
            exclude_paths=get("lines", "exclude_paths", []),
            exclude_commits=[c.lower() for c in get("lines", "exclude_commits", [])],
            top_repos=get("display", "top_repos", d.top_repos),
            top_languages=get("display", "top_languages", d.top_languages),
        )
