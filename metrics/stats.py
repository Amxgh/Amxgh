"""Turns the profile and the user's commits into the figures shown on the card."""

from __future__ import annotations

import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config
from .fuel import Fuel, Tally, fuel, tally
from .gitstats import Commit
from .github import Profile, Repo


@dataclass
class RepoRow:
    label: str
    commits: int
    added: int
    deleted: int
    stars: int
    private: bool


@dataclass
class Month:
    """The current calendar month, day by day, up to today."""
    name: str  # "November"
    key: str  # "2026-11"
    today: int  # day of the month
    days: list[int]  # commits per day, one entry for every day of the month
    added: int
    deleted: int
    best_day: int  # day of the month with the most commits (0 if none yet)
    previous_name: str  # "October"
    previous: int  # commits last month
    record: bool  # more commits than any earlier month

    @property
    def commits(self) -> int:
        return sum(self.days)

    @property
    def active_days(self) -> int:
        return sum(1 for n in self.days if n)


@dataclass
class Summary:
    name: str
    login: str
    updated: str
    since: int  # year of the first commit
    year: int
    commits: int
    added: int
    deleted: int
    commits_this_year: int
    fixes: int  # commits whose subject says fix / bugfix / hotfix
    active_days: int
    longest_streak: int
    busiest_day: int
    busiest_date: str  # "3 Nov 2026"
    pull_requests: int
    merged_pull_requests: int
    month: Month
    hours: list[int]  # commits by hour of day (author's local time), 0-23
    languages: list[tuple[str, int]]  # (language, lines written), "Other" last
    language_count: int
    top_repos: list[RepoRow]
    owned_repos: int
    contributed_repos: int
    stars: int
    forks: int
    organizations: int
    fuel: dict[str, Fuel]  # each coding day's drinks, by ISO date
    month_fuel: Tally
    yesterday: str  # ISO date, for "what did i do yesterday" notes
    night_share: float  # share of all commits made after sunset


_FIX = re.compile(r"\b(?:bug|hot)?fix", re.IGNORECASE)


def _longest_streak(days: set[str]) -> int:
    best = run = 0
    prev = None
    for d in sorted(date.fromisoformat(s) for s in days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def _month(commits: list[Commit], today: date) -> Month:
    key = f"{today:%Y-%m}"
    first = today.replace(day=1)
    prev = first - timedelta(days=1)
    prev_key = f"{prev:%Y-%m}"
    per_month = Counter(c.date[:7] for c in commits)
    this = [c for c in commits if c.date.startswith(key)]
    days = [0] * calendar.monthrange(today.year, today.month)[1]
    for c in this:
        days[int(c.date[8:10]) - 1] += 1
    earlier = [n for m, n in per_month.items() if m < key]
    return Month(
        name=f"{today:%B}",
        key=key,
        today=today.day,
        days=days,
        added=sum(c.added for c in this),
        deleted=sum(c.deleted for c in this),
        best_day=max(range(len(days)), key=lambda i: (days[i], -i)) + 1 if this else 0,
        previous_name=f"{prev:%B}",
        previous=per_month.get(prev_key, 0),
        record=bool(this) and bool(earlier) and len(this) > max(earlier),
    )


def _repo_label(repo: Repo | None, name: str, login: str, show_private: bool) -> str:
    if repo and repo.private and not show_private:
        return f"Private · {repo.language}" if repo.language else "Private repository"
    owner, _, short = name.partition("/")
    return short if owner.lower() == login.lower() else name


def summarize(profile: Profile, commits: list[Commit], cfg: Config) -> Summary:
    now = datetime.now(ZoneInfo(cfg.timezone))
    per_day = Counter(c.date for c in commits)
    busiest = max(per_day, key=lambda d: (per_day[d], d), default=None)

    hours = [0] * 24
    for c in commits:
        hours[c.hour] += 1

    langs: Counter = Counter()
    for c in commits:
        langs.update(c.languages)
    ranked = [(k, v) for k, v in langs.most_common() if v > 0]
    languages = ranked[: cfg.top_languages]
    if rest := sum(v for _, v in ranked[cfg.top_languages :]):
        languages.append(("Other", rest))

    per_repo: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for c in commits:
        row = per_repo[c.repo.lower()]
        row[0] += 1
        row[1] += c.added
        row[2] += c.deleted
    repos = profile.repos
    top = sorted(per_repo.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[: cfg.top_repos]
    top_repos = [
        RepoRow(
            label=_repo_label(repos.get(key), repos[key].name if key in repos else key,
                              profile.login, cfg.show_private_names),
            commits=n, added=a, deleted=d,
            stars=repos[key].stars if key in repos else 0,
            private=repos[key].private if key in repos else False,
        )
        for key, (n, a, d) in top
    ]

    owned = {k: r for k, r in repos.items() if r.owned and not r.fork}
    mine = owned | {k: repos[k] for k in per_repo if k in repos and not repos[k].fork}
    orgs = {repos[k].owner.lower() for k in per_repo if k in repos and repos[k].owner_is_org}

    tz = ZoneInfo(cfg.timezone)
    drinks = fuel(commits, tz, cfg.location)
    night = sum(f.night_commits for f in drinks.values())

    return Summary(
        name=profile.name,
        login=profile.login,
        updated=f"{now.day} {now:%b %Y}",
        since=int(min(per_day)[:4]) if per_day else now.year,
        year=now.year,
        commits=len(commits),
        added=sum(c.added for c in commits),
        deleted=sum(c.deleted for c in commits),
        commits_this_year=sum(1 for c in commits if c.date.startswith(str(now.year))),
        fixes=sum(1 for c in commits if _FIX.search(c.subject)),
        active_days=len(per_day),
        longest_streak=_longest_streak(set(per_day)),
        busiest_day=per_day[busiest] if busiest else 0,
        busiest_date=f"{int(busiest[8:])} {date.fromisoformat(busiest):%b %Y}" if busiest else "",
        pull_requests=profile.pull_requests,
        merged_pull_requests=profile.merged_pull_requests,
        month=_month(commits, now.date()),
        hours=hours,
        languages=languages,
        language_count=len(ranked),
        top_repos=top_repos,
        owned_repos=len(owned),
        contributed_repos=len(per_repo),
        stars=sum(r.stars for r in mine.values()),
        forks=sum(r.forks for r in mine.values()),
        organizations=len(orgs),
        fuel=drinks,
        month_fuel=tally(drinks, f"{now:%Y-%m}"),
        yesterday=(now.date() - timedelta(days=1)).isoformat(),
        night_share=night / len(commits) if commits else 0.0,
    )
