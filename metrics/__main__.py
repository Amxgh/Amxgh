"""Generate the profile metrics card.

    GH_TOKEN=<classic PAT: repo, read:org, read:user, user:email> python -m metrics
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

from .config import Config
from .github import GitHub, Profile, Repo, collect
from .gitstats import Audit, count_lines, dedupe, report, scan_all
from .languages import PathFilter
from .log import log, mask_email, repo_label, warn
from .render import render
from .stats import summarize


def select(profile: Profile, cfg: Config) -> list[Repo]:
    """Repositories worth cloning: the user's own, plus any with commits GitHub attributes
    to them (or that couldn't be checked)."""
    chosen = []
    for key, r in sorted(profile.repos.items()):
        if r.empty or key in cfg.exclude_repos:
            continue
        if key in cfg.include_repos or (r.owned and not r.fork) or r.has_attributed_commits or r.probe_failed:
            chosen.append(r)
    return chosen


def main() -> None:
    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GH_TOKEN must be set to a personal access token")
    cfg = Config.load(os.environ.get("METRICS_CONFIG", "metrics.toml"))

    profile = collect(GitHub(token), cfg.emails, cfg.include_repos)
    if profile.scopes is not None and "repo" not in profile.scopes:
        warn("token lacks the 'repo' scope, so private repositories can't be counted")
    log(f"signed in as {profile.login}; matching commits by {len(profile.emails)} emails: "
        + ", ".join(mask_email(e) for e in sorted(profile.emails)))

    repos = select(profile, cfg)
    log(f"scanning {len(repos)} of {len(profile.repos)} repositories "
        f"({sum(r.private for r in repos)} private)")
    scans = scan_all(repos, profile.emails, Path(cfg.cache_dir), token)

    audit = Audit()
    commits = dedupe(scans, audit)
    paths = PathFilter(cfg.exclude_dirs, cfg.exclude_files, cfg.exclude_paths)
    count_lines(commits, paths, cfg.max_file_lines, cfg.max_commit_lines, cfg.exclude_commits, audit)

    private = {k: r.private for k, r in profile.repos.items()}
    report(commits, scans, audit, private)
    per_repo = Counter(c.repo.lower() for c in commits)
    log("commits per repository:")
    for key, n in per_repo.most_common(20):
        log(f"  {n:>6,}  {repo_label(profile.repos[key].name, private[key])}")
    log(f"(GitHub's own contribution count, default branches only: {profile.github_commit_count:,})")

    summary = summarize(profile, commits, cfg)
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        (out / f"metrics-{theme}.svg").write_text(render(summary, theme), encoding="utf-8")
    log(f"done: {summary.commits:,} commits, +{summary.added:,} / -{summary.deleted:,} lines "
        f"across {summary.contributed_repos} repositories -> {out}/metrics-{{light,dark}}.svg")


if __name__ == "__main__":
    main()
