"""GitHub API: profile, repositories, contribution totals, commit-email discovery."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .log import log, warn

API = "https://api.github.com"

REPO_FIELDS = """
  nameWithOwner owner { login __typename } isPrivate isFork isEmpty
  stargazerCount forkCount diskUsage primaryLanguage { name }
  parent { nameWithOwner } defaultBranchRef { name }
"""


class GitHubError(RuntimeError):
    pass


@dataclass
class Repo:
    name: str  # owner/name
    owner: str
    owner_is_org: bool
    private: bool
    fork: bool
    empty: bool
    stars: int
    forks: int
    disk_kb: int
    language: str | None
    parent: str | None
    default_branch: str | None
    owned: bool
    has_attributed_commits: bool = False
    probe_failed: bool = False

    @classmethod
    def from_node(cls, n: dict, login: str) -> "Repo":
        owner = n["owner"]["login"]
        return cls(
            name=n["nameWithOwner"],
            owner=owner,
            owner_is_org=n["owner"]["__typename"] == "Organization",
            private=n["isPrivate"],
            fork=n["isFork"],
            empty=n["isEmpty"],
            stars=n["stargazerCount"],
            forks=n["forkCount"],
            disk_kb=n["diskUsage"] or 0,
            language=(n.get("primaryLanguage") or {}).get("name"),
            parent=(n.get("parent") or {}).get("nameWithOwner"),
            default_branch=(n.get("defaultBranchRef") or {}).get("name"),
            owned=owner.lower() == login.lower(),
        )


@dataclass
class Profile:
    login: str
    name: str
    user_id: str
    created_at: str
    repos: dict[str, Repo]  # keyed by lower-cased owner/name
    emails: set[str]
    pull_requests: int
    merged_pull_requests: int
    github_commit_count: int  # GitHub's own figure (default branches only), for comparison
    scopes: set[str] | None = field(default=None)


class GitHub:
    def __init__(self, token: str):
        self.token = token
        self.scopes: set[str] | None = None

    def request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            API + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "profile-metrics",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    self._note_scopes(resp.headers)
                    return resp.status, json.loads(resp.read() or b"null")
            except urllib.error.HTTPError as e:
                payload = _json_or_none(e.read())
                limited = e.code in (403, 429) and (
                    e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Remaining") == "0"
                )
                if e.code >= 500 or limited:
                    wait = int(e.headers.get("Retry-After") or 0) or 5 * 2**attempt
                    time.sleep(min(wait, 120))
                    continue
                return e.code, payload
            except (urllib.error.URLError, TimeoutError):
                time.sleep(5 * 2**attempt)
        raise GitHubError(f"{method} {path} failed after retries")

    def graphql(self, query: str, variables: dict | None = None, partial: bool = False):
        status, payload = self.request("POST", "/graphql", {"query": query, "variables": variables or {}})
        if status != 200 or payload is None:
            raise GitHubError(f"GraphQL HTTP {status}: {payload}")
        errors = payload.get("errors")
        if errors and not partial:
            raise GitHubError(f"GraphQL errors: {errors[:3]}")
        return payload.get("data") or {}

    def _note_scopes(self, headers):
        if self.scopes is None and headers.get("X-OAuth-Scopes") is not None:
            self.scopes = {s.strip() for s in headers["X-OAuth-Scopes"].split(",") if s.strip()}


def _json_or_none(raw: bytes):
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def collect(gh: GitHub, extra_emails: list[str], extra_repos: list[str]) -> Profile:
    viewer = gh.graphql(
        """query { viewer {
            id databaseId login name createdAt email
            contributionsCollection { contributionYears }
            pullRequests { totalCount }
            merged: pullRequests(states: MERGED) { totalCount }
        } }"""
    )["viewer"]
    login = viewer["login"]
    repos: dict[str, Repo] = {}

    def add(node):
        if node and node["nameWithOwner"].lower() not in repos:
            repos[node["nameWithOwner"].lower()] = Repo.from_node(node, login)

    # Every repository the token can see: owned, collaborator, and organization repos.
    cursor = None
    while True:
        page = gh.graphql(
            """query($after: String) { viewer { repositories(
                first: 100, after: $after,
                affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
                ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
            ) { pageInfo { hasNextPage endCursor } nodes { %s } } } }""" % REPO_FIELDS,
            {"after": cursor},
        )["viewer"]["repositories"]
        for node in page["nodes"]:
            add(node)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    log(f"{len(repos)} repositories visible to the token")

    # Per-year contribution totals, plus repositories GitHub has recorded contributions
    # to (this is how external open-source repositories get found).
    now = datetime.now(timezone.utc)
    github_commits = 0
    for years in _chunks(viewer["contributionsCollection"]["contributionYears"], 3):
        parts = []
        for y in years:
            end = min(datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
            parts.append(
                f"""y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{end:%Y-%m-%dT%H:%M:%SZ}") {{
                    totalCommitContributions
                    commitContributionsByRepository(maxRepositories: 100) {{ repository {{ {REPO_FIELDS} }} }}
                    pullRequestContributionsByRepository(maxRepositories: 100) {{ repository {{ {REPO_FIELDS} }} }}
                }}"""
            )
        data = gh.graphql("query { viewer { %s } }" % "\n".join(parts))["viewer"]
        for y in years:
            c = data[f"y{y}"]
            github_commits += c["totalCommitContributions"]
            for item in c["commitContributionsByRepository"] + c["pullRequestContributionsByRepository"]:
                add(item["repository"])

    for full in extra_repos:  # repositories named in the config that discovery missed
        if full not in repos and "/" in full:
            owner, name = full.split("/", 1)
            node = gh.graphql(
                "query($o: String!, $n: String!) { repository(owner: $o, name: $n) { %s } }" % REPO_FIELDS,
                {"o": owner, "n": name}, partial=True,
            ).get("repository")
            if node:
                add(node)
            else:
                warn(f"[repos].include: {full} not found or not accessible")

    emails = {
        f"{viewer['databaseId']}+{login}@users.noreply.github.com".lower(),
        f"{login}@users.noreply.github.com".lower(),
        *extra_emails,
    }
    if viewer.get("email"):
        emails.add(viewer["email"].lower())
    status, body = gh.request("GET", "/user/emails")
    if status == 200:
        emails |= {e["email"].lower() for e in body if e.get("verified")}
    else:
        warn("could not read /user/emails (token lacks the user:email scope); relying on discovery")

    emails |= _probe(gh, viewer["id"], [r for r in repos.values() if not r.empty])

    return Profile(
        login=login,
        name=viewer["name"] or login,
        user_id=viewer["id"],
        created_at=viewer["createdAt"],
        repos=repos,
        emails=emails,
        pull_requests=viewer["pullRequests"]["totalCount"],
        merged_pull_requests=viewer["merged"]["totalCount"],
        github_commit_count=github_commits,
        scopes=gh.scopes,
    )


_PROBE = """r%d: repository(owner: %s, name: %s) {
  defaultBranchRef { target { ... on Commit {
    history(first: 100, author: {id: $uid}) { nodes { author { email } } }
  } } }
  refs(refPrefix: "refs/heads/", first: 50, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
    nodes { target { ... on Commit { history(first: 1, author: {id: $uid}) { totalCount } } } }
  }
}"""


def _probe(gh: GitHub, user_id: str, repos: list[Repo]) -> set[str]:
    """Ask GitHub which repos have commits attributed to the user on any recent branch,
    and collect the commit emails GitHub links to the account."""
    emails: set[str] = set()

    def run(batch: list[Repo]) -> list[Repo]:
        parts = []
        for i, r in enumerate(batch):
            owner, name = r.name.split("/", 1)
            parts.append(_PROBE % (i, json.dumps(owner), json.dumps(name)))
        try:
            data = gh.graphql("query($uid: ID!) {\n%s\n}" % "\n".join(parts), {"uid": user_id}, partial=True)
        except GitHubError:
            return batch
        failed = []
        for i, r in enumerate(batch):
            node = data.get(f"r{i}")
            if node is None:
                failed.append(r)
                continue
            target = ((node.get("defaultBranchRef") or {}).get("target")) or {}
            for c in (target.get("history") or {}).get("nodes", []):
                if c.get("author", {}).get("email"):
                    emails.add(c["author"]["email"].lower())
            refs = ((node.get("refs") or {}).get("nodes")) or []
            r.has_attributed_commits = any(
                ((ref.get("target") or {}).get("history") or {}).get("totalCount", 0) > 0 for ref in refs
            )
        return failed

    retry = []
    for batch in _chunks(repos, 5):
        retry += run(batch)
    for r in retry:  # one at a time, so a single slow repository can't sink a batch
        if run([r]):
            r.probe_failed = True
    return emails
