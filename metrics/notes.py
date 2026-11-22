"""The handwritten notes scribbled on the card.

What they say lives in scribbles.toml at the top of the repository. This module works
out which groups of lines there apply to the current numbers, and fills in the values.

Every note has a pool of lines. Each workflow run moves every pool on to its next
line, in a shuffled order, so a line only comes back once its whole pool has had a
turn. Lines that don't fit their spot on the card are skipped at render time.
"""

from __future__ import annotations

import os
import random
import tomllib
from datetime import date, timedelta
from functools import cache
from pathlib import Path

from .fmt import compact, hour, ordinal
from .log import warn
from .stats import Month, Summary

SCRIBBLES = Path(__file__).resolve().parent.parent / "scribbles.toml"

# The workflow's run number, so every regeneration picks new lines. Outside Actions
# it's the date, so local previews are stable for a day.
RUN = int(os.environ.get("GITHUB_RUN_NUMBER") or date.today().toordinal())


def ordered(slot: str, options: list) -> list:
    """The pool in this slot's shuffled order, starting from this run's turn."""
    if not options:
        return []
    order = list(range(len(options)))
    random.Random(f"{slot}/{len(options)}").shuffle(order)
    k = RUN % len(order)
    return [options[i] for i in order[k:] + order[:k]]


def _ascii(option) -> bool:
    parts = (option,) if isinstance(option, str) else option
    return all(p.isascii() for p in parts if isinstance(p, str))


def pick(slot: str, options: list, fits=None):
    """This run's line for the slot, from the lines that fit (so consecutive runs differ)."""
    fitting = [o for o in options if _ascii(o) and (fits is None or fits(o))]
    return ordered(slot, fitting)[0] if fitting else None


# ---- Reading scribbles.toml ----

class Count(int):
    """A number in a line: {n} prints 1,234, and {n:one|many} picks the word that agrees
    with it, with # standing for the number itself."""

    def __format__(self, spec: str) -> str:
        if "|" in spec:
            one, _, many = spec.partition("|")
            return (one if self == 1 else many).replace("#", format(int(self), ","))
        return format(int(self), spec or ",")


_warned: set[str] = set()


def _warn_once(msg: str) -> None:
    if msg not in _warned:
        _warned.add(msg)
        warn(f"{SCRIBBLES.name}: {msg}")


@cache
def _scribbles() -> dict:
    try:
        return tomllib.loads(SCRIBBLES.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{SCRIBBLES}: {e}") from None


def _section(name: str) -> dict:
    """The [name] table, or {} if it's missing or switched off with `off = true`.
    An empty group (or a missing one) simply adds no lines."""
    table = dict(_scribbles().get(name, {}))
    off = table.pop("off", False)
    if not isinstance(off, bool):
        _warn_once(f"[{name}] off has to be true or false, not {off!r}; leaving it on")
        off = False
    return {} if off else table


def _fill(section: str, line, values: dict):
    """The line with its {names} filled in, or None (after a warning) if it can't be.
    [hero] lines may be split over several lines, and come back as tuples."""
    multi = section == "hero"
    parts = [line] if isinstance(line, str) else line
    if not (isinstance(parts, list) and parts and all(isinstance(p, str) for p in parts)):
        _warn_once(f"[{section}] skipping {line!r}: a line has to be a string")
        return None
    if len(parts) > 1 and not multi:
        _warn_once(f"[{section}] skipping {line!r}: only [hero] lines can be split over lines")
        return None
    if not all(p.isascii() for p in parts):
        _warn_once(f"[{section}] skipping {line!r}: the handwriting font only has plain ASCII")
        return None
    try:
        filled = tuple(p.format_map(values) for p in parts)
    except KeyError as e:
        names = ", ".join(f"{{{k}}}" for k in values) or "none"
        _warn_once(f"[{section}] skipping {line!r}: no {{{e.args[0]}}} here (this section has {names})")
        return None
    except (ValueError, IndexError, AttributeError, TypeError) as e:
        _warn_once(f"[{section}] skipping {line!r}: {e} (write {{{{ and }}}} for literal braces)")
        return None
    return filled if multi else filled[0]


def _fill_all(section: str, lines, values: dict) -> list:
    lines = [lines] if isinstance(lines, str) else lines
    return [f for f in (_fill(section, line, values) for line in lines) if f is not None]


def _lines(section: str, when: dict[str, bool], **values) -> list:
    """Every line in the section's groups whose condition holds, in file order."""
    out = []
    for group, lines in _section(section).items():
        if not isinstance(lines, (list, str)):
            continue  # a setting or a sub-table, not a group of lines
        if group not in when:
            _warn_once(f"[{section}] has no group called '{group}', so its lines are never used "
                       f"(the groups are: {', '.join(when)})")
            continue
        if when[group]:
            out += _fill_all(section, lines, values)
    return out


# ---- Beside the all-time total (one or two lines, arrow points at "commits since") ----

def hero(s: Summary) -> list[tuple[str, ...]]:
    n, fixes, this_year = s.commits, s.fixes, s.commits_this_year
    per_day = n / s.active_days if s.active_days else 0
    return _lines("hero", {
        "always": True,
        "night_owl": s.night_share >= 0.25,
        "coding_days": s.active_days > 0,
        "busy_days": per_day >= 4,
        "fixes": 0 < fixes < n,
        "this_year": 0 < this_year < n,
        "mostly_this_year": 0 < this_year < n and this_year / n >= 0.5,
        "deleted": s.deleted > 0,
        "net_growth": s.added > s.deleted,
        "streak": s.longest_streak >= 5,
    },
        commits=Count(n), year=str(s.year), fixes=Count(fixes), non_fixes=Count(n - fixes),
        this_year=Count(this_year), this_year_pct=Count(round(100 * this_year / n) if n else 0),
        night_pct=Count(round(100 * s.night_share)), active_days=Count(s.active_days),
        per_day=Count(round(per_day)), streak=Count(s.longest_streak),
        added=compact(s.added), deleted=compact(s.deleted), net=compact(s.added - s.deleted),
    )


# ---- Under this month's chart ----

def month(m: Month) -> list[str]:
    n, last = m.commits, m.previous
    left = len(m.days) - m.today
    record = bool(n) and m.record
    usual = bool(n) and not record
    return _lines("month", {
        "nothing_yet": not n,
        "nothing_yet_vs_last_month": not n and last > 0,
        "record_so_far": record and left > 0,
        "record_so_far_vs_last_month": record and left > 0 and last > 0,
        "record": record and not left,
        "behind_last_month": usual and last > n,
        "ahead_of_last_month": usual and 0 < last <= n,
        "none_last_month": usual and not last,
    },
        commits=Count(n), month=m.name, last_commits=Count(last), last_month=m.previous_name,
        today=Count(m.today), today_nth=ordinal(m.today), days_left=Count(left),
        behind=Count(max(last - n, 0)), ahead=Count(max(n - last, 0)),
    )


# ---- Beside the best day of the month (short: it has to fit next to a bar) ----

def best_day(m: Month, s: Summary) -> list[str]:
    earlier = m.best_day != m.today
    v = m.days[m.best_day - 1] if m.best_day else 0
    f = s.fuel.get(f"{m.key}-{m.best_day:02}") if earlier else None
    one_red_bull = bool(f and f.red_bulls and f.red_bulls != 2)
    return _lines("best_day", {
        "today": not earlier,
        "earlier": earlier,
        "all_time_record": earlier and v == s.busiest_day,
        "weekend": bool(f and f.weekend),
        "latte": bool(f and f.latte),
        "two_red_bulls": bool(f and f.red_bulls == 2),
        "latte_and_red_bull": one_red_bull and f.latte,
        "red_bull": one_red_bull and not f.latte,
        "finished": bool(f and f.beer == "done"),
    }, day=ordinal(m.best_day), commits=Count(v), beer=f.brand if f else "")


# ---- After "N pull requests opened, M merged" ----

def pull_requests(s: Summary) -> list[str]:
    pr, merged = s.pull_requests, s.merged_pull_requests
    unmerged = pr - merged
    return _lines("pull_requests", {
        "all_merged": pr > 0 and not unmerged,
        "mostly_merged": pr > 0 and unmerged != 0 and unmerged <= pr * 0.2,
        "some_merged": pr > 0 and unmerged > pr * 0.2,
    },
        opened=Count(pr), merged=Count(merged), unmerged=Count(unmerged),
        merge_rate=Count(round(100 * merged / pr) if pr else 0),
    )


# ---- After "N commits in a single day" ----

def busiest(s: Summary) -> list[str]:
    return _lines("busiest", {"big_day": s.busiest_day >= 20}, commits=Count(s.busiest_day))


# ---- Under the facts: what I was drinking, from when the commits happened ----

def fuel(s: Summary) -> list[str]:
    if not s.fuel:
        return []
    table = _section("fuel")
    key, f = list(s.fuel.items())[-1]
    recent = (date.fromisoformat(s.yesterday) - date.fromisoformat(key)).days < 6
    weekday = recent and not f.weekend

    # how to say that coding day, for daytime and for nighttime
    today = (date.fromisoformat(s.yesterday) + timedelta(days=1)).isoformat()
    when = "today" if key == today else "yesterday" if key == s.yesterday else "earlier"
    name = {"weekday": date.fromisoformat(key).strftime("%A").lower()}
    names = table.get("names", {}).get(when, {})
    day = _fill("fuel.names", names.get("day", "{weekday}"), name) or name["weekday"]
    night = _fill("fuel.names", names.get("night", "{weekday}"), name) or name["weekday"]

    y = s.fuel.get(s.yesterday)
    t = s.month_fuel
    pumps = table.get("pumps_per_latte", 8)
    return _lines("fuel", {
        "weekend": recent and f.weekend,
        "latte": weekday and f.latte,
        "two_red_bulls": weekday and f.red_bulls == 2,
        "red_bull": weekday and f.red_bulls not in (0, 2),
        "finished": weekday and f.beer == "done",
        "fixing": weekday and f.beer == "fixing",
        "committed_yesterday": bool(y and y.commits),
        "day_off_yesterday": s.yesterday not in s.fuel,
        "caffeine_and_beer": bool(t.beers and (t.lattes or t.red_bulls)),
        "lattes": t.lattes >= 3,
    },
        day=day, night=night, beer=f.brand, night_commits=Count(f.night_commits),
        lattes=Count(t.lattes), red_bulls=Count(t.red_bulls), beers=Count(t.beers),
        pumps=Count(pumps * t.lattes if isinstance(pumps, int) else 0),
    )


# ---- Under the commit clock, after the busiest hour ----

def hours(h: int) -> list[str]:
    groups = {}
    for start, lines in _section("hours").items():
        if start.isdigit() and int(start) < 24:
            groups[int(start)] = lines
        else:
            _warn_once(f"[hours] groups are named by the hour they start at (0-23), not '{start}'")
    starts = [k for k in groups if k <= h]
    return _fill_all("hours", groups[max(starts)], {"hour": hour(h)}) if starts else []


# ---- Beside the "languages" heading ----

def languages(langs: list[tuple[str, int]]) -> list[str]:
    named = [(name, v) for name, v in langs if name != "Other"]
    if not named:
        return []
    share = named[0][1] / sum(v for _, v in langs)
    several = len(named) > 1
    return _lines("languages", {
        "mostly_one": share >= 0.5 and several,
        "only_one": share >= 0.5 and not several,
        "mixed": share < 0.5,
    }, top=named[0][0].lower(), second=named[1][0].lower() if several else "",
        top_pct=Count(round(100 * share)))


# ---- Beside one of the other languages in the list ----

def language_row(name: str, share: float, hidden: int) -> list[str]:
    other = name == "Other"
    values = {"language": name, "hidden": Count(hidden)}
    own = [] if other else _section("language_row").get("by_language", {}).get(name, [])
    return _fill_all("language_row", own, values) + _lines("language_row", {
        "tiny": not other and share < 0.02,
        "other": other,
        "other_several": other and hidden > 1,
    }, **values)


# ---- Under the repositories ----

def repos(s: Summary) -> list[str]:
    top = s.top_repos[0] if s.top_repos and s.commits else None
    share = round(100 * top.commits / s.commits) if top else 0
    public = bool(top and not top.private)
    private = sum(r.private for r in s.top_repos) if top else 0
    return _lines("repos", {
        "always": True,
        "big_share": share >= 20,
        "big_share_public": share >= 20 and public,
        "top_repo_deletions": public and top.deleted >= 1000,
        "one_private": private == 1,
        "several_private": private > 1,
        "any_private": private > 0,
        "stars": s.stars > 0,
        "forks": s.forks > 0,
        "orgs": s.organizations > 0,
        "own_repos": s.owned_repos >= 2,
        "get_around": s.contributed_repos > s.owned_repos,
    },
        top_repo=top.label if top else "", share=Count(share),
        top_repo_deleted=compact(top.deleted) if top else "0", private=Count(private),
        stars=Count(s.stars), forks=Count(s.forks), orgs=Count(s.organizations),
        owned_repos=Count(s.owned_repos), contributed_repos=Count(s.contributed_repos),
    )


# ---- The printed footer ----

def footer() -> list[str]:
    return _lines("footer", {"always": True})
