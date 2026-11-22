"""Commit analysis over local bare clones.

Only commits the user authored are kept (matched by author email), from every
branch, merges excluded. Copies of the same change are counted once:
  * the same SHA in several repos (forks, mirrors);
  * rebased or cherry-picked copies (same author timestamp and subject);
  * branch commits that were squash-merged into the default branch (their subjects
    appear in the squash commit's "* subject" list).
Line counts then skip lockfiles, vendored/generated/data paths and oversized changes.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .github import Repo
from .languages import PathFilter, language_of
from .log import log, mask_email, repo_label, warn

_REC = "\x1e"
_FLD = "\x1f"
_SQUASH_SUBJECT = re.compile(r"\(#\d+\)\s*$")


@dataclass
class Commit:
    sha: str
    repo: str
    email: str
    name: str
    timestamp: int
    date: str  # YYYY-MM-DD in the author's own timezone
    subject: str
    files: list[tuple[int, int, str]]  # (added, deleted, path); binary files dropped
    on_default: bool = False
    network: str = ""
    added: int = 0
    deleted: int = 0
    languages: Counter = field(default_factory=Counter)


@dataclass
class RepoScan:
    repo: Repo
    commits: list[Commit]
    squashed_subjects: set[str]
    other_emails: Counter  # (name, email) -> commits, for emails not known to be the user's


@dataclass
class Audit:
    filtered_lines: int = 0
    big_files: list[tuple[int, Commit, str]] = field(default_factory=list)
    big_commits: list[tuple[int, Commit]] = field(default_factory=list)
    manual: list[Commit] = field(default_factory=list)
    duplicate_copies: int = 0
    squash_copies: int = 0


def git_env(token: str | None) -> dict:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    if token:  # passed through the environment so it never lands in a cached repo config
        cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {cred}",
        }
    return env


def _git(args: list[str], env: dict, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], env=env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args[:3], proc.stdout, proc.stderr)
    return proc.stdout


def sync(repo: Repo, root: Path, env: dict, blobless_above_kb: int = 300_000) -> Path | None:
    """Bare-clone the repository's branches, or fetch if a cached clone exists."""
    path = root / (repo.name.replace("/", "__") + ".git")
    url = f"https://github.com/{repo.name}.git"
    fetch = ["-C", str(path), "fetch", "--quiet", "--prune", "--no-tags", "--update-head-ok",
             "origin", "+refs/heads/*:refs/heads/*"]
    try:
        if (path / "HEAD").exists():
            try:
                _git(["-C", str(path), "remote", "set-url", "origin", url], env)
                _git(fetch, env)
            except subprocess.CalledProcessError:
                shutil.rmtree(path, ignore_errors=True)  # broken cache entry: start over
        if not (path / "HEAD").exists():
            clone = ["clone", "--quiet", "--bare", "--no-tags"]
            if repo.disk_kb > blobless_above_kb:  # huge repo: fetch file contents lazily
                clone.append("--filter=blob:none")
            _git(clone + [url, str(path)], env)
        if repo.default_branch:
            _git(["-C", str(path), "symbolic-ref", "HEAD", f"refs/heads/{repo.default_branch}"], env)
        return path
    except subprocess.CalledProcessError as e:
        reason = (e.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        warn(f"skipping {repo_label(repo.name, repo.private)}: {reason[0]}")
        return None


def _real_path(numstat_path: str) -> str:
    """Resolve numstat rename notation ("a/{old => new}/b", "old => new") to the new path."""
    if " => " not in numstat_path:
        return numstat_path
    if "{" in numstat_path and "}" in numstat_path:
        pre, rest = numstat_path.split("{", 1)
        mid, post = rest.split("}", 1)
        new = mid.split(" => ", 1)[1]
        return re.sub(r"/{2,}", "/", pre + new + post).lstrip("/")
    return numstat_path.split(" => ", 1)[1]


def scan(path: Path, repo: Repo, emails: set[str], env: dict) -> RepoScan:
    authors = [f"--author=<{e}>" for e in sorted(emails)]
    base = ["-C", str(path), "-c", "core.quotepath=off", "log", "--no-merges",
            "--fixed-strings", "--regexp-ignore-case", *authors]

    out = _git(base + ["--all", "--numstat", "-M",
                       f"--format={_REC}%H{_FLD}%ae{_FLD}%an{_FLD}%at{_FLD}%ai{_FLD}%s"], env)
    commits = []
    for record in out.split(_REC)[1:]:
        header, _, body = record.partition("\n")
        sha, email, name, ts, iso, subject = header.split(_FLD, 5)
        if email.lower() not in emails:
            continue
        files = []
        for line in body.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3 and parts[0] != "-":
                files.append((int(parts[0]), int(parts[1]), _real_path(parts[2])))
        commits.append(Commit(sha, repo.name, email.lower(), name, int(ts), iso[:10], subject.strip(), files))

    # Which of those commits are on the default branch, and what squash merges contain.
    squashed: set[str] = set()
    on_default: set[str] = set()
    out = _git(base + ["HEAD", f"--format={_REC}%H{_FLD}%B"], env, check=False)
    for record in out.split(_REC)[1:]:
        sha, _, message = record.partition(_FLD)
        on_default.add(sha)
        lines = message.strip().splitlines()
        if lines and _SQUASH_SUBJECT.search(lines[0]):
            squashed |= {ln[2:].strip() for ln in lines[1:] if ln.startswith("* ")}
    for c in commits:
        c.on_default = c.sha in on_default

    # Commits under the user's name but an unknown email: suggest them in the log.
    names = {c.name.lower() for c in commits}
    other = Counter()
    if names:
        for line in _git(["-C", str(path), "shortlog", "-sne", "--all"], env, check=False).splitlines():
            m = re.match(r"\s*(\d+)\t(.*) <(.*)>$", line)
            if m and m.group(2).lower() in names and m.group(3).lower() not in emails:
                other[m.group(3).lower()] += int(m.group(1))
    return RepoScan(repo, commits, squashed, other)


def scan_all(repos: list[Repo], emails: set[str], cache: Path, token: str | None) -> list[RepoScan]:
    cache.mkdir(parents=True, exist_ok=True)
    env = git_env(token)

    def work(repo: Repo) -> RepoScan | None:
        path = sync(repo, cache, env)
        return scan(path, repo, emails, env) if path else None

    with ThreadPoolExecutor(max_workers=6) as pool:
        return [s for s in pool.map(work, repos) if s]


def dedupe(scans: list[RepoScan], audit: Audit) -> list[Commit]:
    # Originals before forks and owned repos first, so shared commits are credited there.
    scans = sorted(scans, key=lambda s: (s.repo.fork, not s.repo.owned, s.repo.name.lower()))
    by_sha: dict[str, Commit] = {}
    by_change: dict[tuple[int, str], Commit] = {}
    landed: set[str] = set()
    squashed: dict[str, set[str]] = defaultdict(set)
    for s in scans:
        network = (s.repo.parent if s.repo.fork and s.repo.parent else s.repo.name).lower()
        squashed[network] |= s.squashed_subjects
        for c in s.commits:
            if c.on_default:
                landed.add(c.sha)
            if c.sha in by_sha:
                continue
            copy = by_change.get((c.timestamp, c.subject))
            if copy:
                audit.duplicate_copies += 1
                if c.on_default:
                    landed.add(copy.sha)
                continue
            c.network = network
            by_sha[c.sha] = by_change[(c.timestamp, c.subject)] = c

    kept = []
    for c in by_sha.values():
        c.on_default = c.sha in landed
        if not c.on_default and c.subject in squashed[c.network]:
            audit.squash_copies += 1
            continue
        kept.append(c)
    return kept


def count_lines(commits: list[Commit], paths: PathFilter, max_file: int, max_commit: int,
                excluded_shas: list[str], audit: Audit) -> None:
    for c in commits:
        if any(c.sha.startswith(p) for p in excluded_shas):
            audit.manual.append(c)
            continue
        added = deleted = 0
        langs: Counter = Counter()
        for a, d, path in c.files:
            if paths.excluded(c.repo, path):
                audit.filtered_lines += a + d
                continue
            if a + d > max_file:
                audit.big_files.append((a + d, c, path))
                continue
            added += a
            deleted += d
            if lang := language_of(path):
                langs[lang] += a
        if added + deleted > max_commit:
            audit.big_commits.append((added + deleted, c))
            continue
        c.added, c.deleted, c.languages = added, deleted, langs


def report(commits: list[Commit], scans: list[RepoScan], audit: Audit, private: dict[str, bool]) -> None:
    """Print an audit trail to the log so the numbers can be checked."""
    def label(c: Commit) -> str:
        return repo_label(c.repo, private.get(c.repo.lower(), True))

    def subject(c: Commit) -> str:
        return "" if private.get(c.repo.lower(), True) else f"  {c.subject[:60]}"

    log(f"kept {len(commits)} commits; dropped {audit.duplicate_copies} rebased/cherry-picked copies "
        f"and {audit.squash_copies} squash-merged branch commits")
    log(f"lines in lockfiles/vendored/generated/data paths (not counted): {audit.filtered_lines:,}")
    for n, c, path in sorted(audit.big_files, key=lambda t: -t[0])[:10]:
        shown = path if not private.get(c.repo.lower(), True) else "*" + os.path.splitext(path)[1]
        log(f"  oversized file skipped: {n:>8,}  {c.sha[:8]}  {label(c)}  {shown}")
    for n, c in sorted(audit.big_commits, key=lambda t: -t[0])[:10]:
        log(f"  oversized commit skipped: {n:>8,}  {c.sha[:8]}  {label(c)}{subject(c)}")
    for c in audit.manual:
        log(f"  excluded by config: {c.sha[:8]}  {label(c)}")
    log("largest commits counted (add a SHA to [lines].exclude_commits if one isn't yours):")
    for c in sorted(commits, key=lambda c: -(c.added + c.deleted))[:10]:
        log(f"  {c.added + c.deleted:>8,}  {c.sha[:8]}  {label(c)}{subject(c)}")

    other = Counter()
    for s in scans:
        other.update(s.other_emails)
    if other:
        log("commits under your name with emails not linked to your account "
            "(add yours to [authorship].emails):")
        for email, n in other.most_common(8):
            log(f"  {n:>6}  {mask_email(email)}")
