"""Turns the profile and the user's commits into the figures shown on the card."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config
from .gitstats import Commit
from .github import Profile, Repo


@dataclass
class RepoRow:
    label: str
    commits: int
    added: int
    deleted: int
    stars: int


@dataclass
class Summary:
    name: str
    login: str
    updated: str
    commits: int
    added: int
    deleted: int
    commits_year: int
    added_year: int
    deleted_year: int
    active_days: int
    longest_streak: int
    busiest_day: int
    pull_requests: int
    merged_pull_requests: int
    reviews: int
    issues: int
    monthly: list[tuple[str, int]]  # ("2024-03", commits)
    languages: list[tuple[str, int]]  # (language, lines written), "Other" last
    language_count: int
    top_repos: list[RepoRow]
    owned_repos: int
    contributed_repos: int
    stars: int
    forks: int
    organizations: int


def _longest_streak(days: set[str]) -> int:
    best = run = 0
    prev = None
    for d in sorted(date.fromisoformat(s) for s in days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def _months(first: str, last: str, limit: int) -> list[str]:
    y, m = map(int, last.split("-"))
    out = []
    while len(out) < limit:
        key = f"{y:04d}-{m:02d}"
        out.append(key)
        if key <= first:
            break
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def _repo_label(repo: Repo | None, name: str, login: str, show_private: bool) -> str:
    if repo and repo.private and not show_private:
        return f"Private · {repo.language}" if repo.language else "Private repository"
    owner, _, short = name.partition("/")
    return short if owner.lower() == login.lower() else name


def summarize(profile: Profile, commits: list[Commit], cfg: Config) -> Summary:
    now = datetime.now(ZoneInfo(cfg.timezone))
    year_ago = now.timestamp() - 365 * 86400
    recent = [c for c in commits if c.timestamp >= year_ago]
    per_day = Counter(c.date for c in commits)

    per_month = Counter(c.date[:7] for c in commits)
    this_month = now.strftime("%Y-%m")
    first = min(per_month) if per_month else this_month
    monthly = [(m, per_month.get(m, 0)) for m in _months(first, this_month, cfg.chart_months)]

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
        )
        for key, (n, a, d) in top
    ]

    owned = {k: r for k, r in repos.items() if r.owned and not r.fork}
    mine = owned | {k: repos[k] for k in per_repo if k in repos and not repos[k].fork}
    orgs = {repos[k].owner.lower() for k in per_repo if k in repos and repos[k].owner_is_org}

    return Summary(
        name=profile.name,
        login=profile.login,
        updated=f"{now.day} {now:%b %Y}",
        commits=len(commits),
        added=sum(c.added for c in commits),
        deleted=sum(c.deleted for c in commits),
        commits_year=len(recent),
        added_year=sum(c.added for c in recent),
        deleted_year=sum(c.deleted for c in recent),
        active_days=len(per_day),
        longest_streak=_longest_streak(set(per_day)),
        busiest_day=max(per_day.values(), default=0),
        pull_requests=profile.pull_requests,
        merged_pull_requests=profile.merged_pull_requests,
        reviews=profile.reviews,
        issues=profile.issues,
        monthly=monthly,
        languages=languages,
        language_count=len(ranked),
        top_repos=top_repos,
        owned_repos=len(owned),
        contributed_repos=len(per_repo),
        stars=sum(r.stars for r in mine.values()),
        forks=sum(r.forks for r in mine.values()),
        organizations=len(orgs),
    )
