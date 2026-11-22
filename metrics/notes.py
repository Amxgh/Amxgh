"""The handwritten notes scribbled on the card.

Every note has a pool of lines, most of them filled in from the stats. Each workflow
run moves every pool on to its next line, in a shuffled order, so a line only comes
back once its whole pool has had a turn. Lines that don't fit their spot on the card
are skipped at render time, and lines whose premise doesn't hold for the current
numbers are never offered.

Keep lines to plain ASCII: the embedded handwriting font only covers ASCII.
"""

from __future__ import annotations

import os
import random
from datetime import date, timedelta

from .fmt import compact, hour, ordinal, plural
from .stats import Month, Summary

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


# ---- Beside the all-time total (one or two lines, arrow points at "commits since") ----

def hero(s: Summary) -> list[tuple[str, ...]]:
    n, fixes, this_year = s.commits, s.fixes, s.commits_this_year
    out: list[tuple[str, ...]] = [
        ("and not one of them", "is a merge commit"),
        ("git log goes brrr",),
        ("ctrl+s is my", "cardio"),
        ("each one a tiny", "act of hope"),
        ("all of them", "absolutely necessary"),
        ("ask me about", "literally any of them"),
        ("hand-crafted,", "artisanal commits"),
        ("some of them", "even have tests"),
        ("every one of them", "pushed with confidence"),
        ("a few of them", "were on purpose"),
        ("my keyboard", "has seen things"),
        ("and i'd do it", "all again"),
        ("fueled by lattes,", "red bull zero and heineken"),
        ("headphones on.", "music off. locked in."),
        ("the easy ones were", "written to kiss land"),
        ("each one worth", "a cold heineken"),
        ("hold my beer",),
        ("never once mixed", "caffeine and beer"),
        ("iced sf vanilla", "protein latte. always."),
        ("4 sf vanilla, 4 sf caramel,", "3 long shots"),
    ]
    if s.night_share >= 0.25:
        pct = round(100 * s.night_share)
        out += [(f"{pct}% of them after sunset,", "from bed"),
                (f"{pct}% written in bed.", "the rest on campus")]
    if s.active_days:
        out.append((f"{s.active_days:,} days of this.", "and counting"))
        per_day = n / s.active_days
        if per_day >= 4:
            out.append((f"~{round(per_day)} per coding day.", "pacing is optional"))
    if 0 < fixes < n:
        one = fixes == 1
        noun, verb, say = ("fix", "fixes", "says") if one else ("fixes", "fix", "say")
        out += [
            (f"{fixes:,} of them", f"{verb} the other {n - fixes:,}"),
            (f'{fixes:,} of them {say} "fix"', "the rest are lying"),
            (f"{fixes:,} {noun},", f"{n - fixes:,} future bugs"),
            (f"{fixes:,} {say} fix.", "the rest will, eventually"),
            (f"{fixes:,} {noun}.", "for very good reasons"),
        ]
    if 0 < this_year < n:
        out.append((f"{this_year:,} of them", f"{'was' if this_year == 1 else 'were'} this year alone"))
        if this_year / n >= 0.5:
            out += [(f"{round(100 * this_year / n)}% of them", f"happened in {s.year}"),
                    (f"{s.year} has been", "a lot")]
    if s.deleted:
        out.append((f"deleted {compact(s.deleted)} lines.", "my finest work"))
    if s.added > s.deleted:
        out.append((f"net +{compact(s.added - s.deleted)} lines.", "the codebase grows"))
    if s.longest_streak >= 5:
        out.append((f"best streak: {s.longest_streak} days.", "then i blinked"))
    return out


# ---- Under this month's chart ----

def month(m: Month) -> list[str]:
    n, prev, p, name = m.commits, m.previous_name, m.previous, m.name
    left = len(m.days) - m.today
    if not n:
        out = ["nothing yet. thinking very hard.", "blank page. full potential.",
               f"day {m.today}. the keyboard is warming up.", "stretching. hydrating. soon.",
               "laundry. meal prep. a new show. soon.", "movie marathon first. commits later."]
        if p:
            out += [f"{prev} had {p:,}. recovering.", f"{prev} had {p:,}. resting my fingers.",
                    f"{prev}: {p:,}. {name}: loading..."]
        return out
    if m.record and left:
        out = [f"my biggest month ever. it's the {ordinal(m.today)}.",
               f"personal record, and it's only the {ordinal(m.today)}",
               "new high score. please send snacks.",
               f"biggest month yet. {left} {plural(left, 'day')} to go.",
               "all-time record. my keyboard filed a complaint.",
               "record month. sleep has been postponed.",
               f"best month ever. {name} is unwell.",
               "record month. red bull zero stocks are low."]
        if p:
            out.append(f"{prev} had {p:,}. {name} said hold my beer.")
        return out
    if m.record:
        return ["my biggest month ever.", "record month. time for a nap.",
                f"new record. {name}, you were a lot.", "record month. heineken time."]
    if p > n:
        return [f"{prev} had {p:,}. catching up.",
                f"{p - n:,} behind {prev}. the comeback starts now.",
                f"{prev} set the bar at {p:,}. working on it.",
                f"quiet one so far. {prev} was {p:,}.",
                f"{prev}: {p:,}. {name}: pacing myself. allegedly.",
                f"{prev}: {p:,}. {name}: gym, laundry, a new show."]
    if p:
        return [f"already beat {prev} ({p:,}).", f"{prev} had {p:,}. we're past that.",
                f"{n - p:,} ahead of {prev}. smooth.", f"sorry {prev}, you've been lapped."]
    return ["first month on the board.", "and so it begins.", "off to a running start."]


# ---- Beside the best day of the month (short: it has to fit next to a bar) ----

def best_day(m: Month, s: Summary) -> list[str]:
    if m.best_day == m.today:
        return ["today. still going.", "today. send help.", "that's today. hi.",
                "today, apparently.", "today. it's not over."]
    d = ordinal(m.best_day)
    v = m.days[m.best_day - 1]
    out = [f"the {d}. long day.", f"the {d}. no comment.", f"the {d}. a blur.",
           f"the {d}. in the zone.", f"the {d}. deadline?",
           f"the {d}. good times.", f"{v} on the {d}. hm.", f"the {d}. what a day."]
    if v == s.busiest_day:
        out += [f"the {d}. all-time record.", f"the {d}. a new record."]
    if f := s.fuel.get(f"{m.key}-{m.best_day:02}"):
        if f.weekend:
            out += [f"the {d}. weekend. {f.brand}.", f"the {d}. zero caffeine."]
        if f.latte:
            out.append(f"the {d}. latte: yes.")
        if f.red_bulls == 2:
            out += [f"the {d}. 2 red bulls.", f"the {d}. two cans deep."]
        elif f.red_bulls and f.latte:
            out.append(f"the {d}. latte + red bull.")
        elif f.red_bulls:
            out.append(f"the {d}. red bull zero.")
        if f.beer == "done":
            out += [f"the {d}. then {f.brand}.", f"the {d}. done. {f.brand}."]
    return out


# ---- After "N pull requests opened, M merged" ----

def pull_requests(s: Summary) -> list[str]:
    pr, merged = s.pull_requests, s.merged_pull_requests
    rest = pr - merged
    if not pr:
        return []
    if not rest:
        return ["every single one.", "a perfect record. for now.", "all merged. no notes.",
                "100%. don't jinx it."]
    rate = round(100 * merged / pr)
    if rest <= pr * 0.2:
        one = rest == 1
        other = "the other one" if one else f"the other {rest}"
        return [f"we don't talk about {other}", f"{other} {'is' if one else 'are'} in a better place",
                f"rip to {other}", f"{other} {'was' if one else 'were'} character building",
                f"{rest} got away", f"{rest} still out there somewhere", f"{rate}% merge rate. not bad.",
                f"{other}? never heard of {'it' if one else 'them'}"]
    return [f"{rate}% merged. the rest are cooking", "some were just vibes", "the rest are still in review. forever."]


# ---- After "N commits in a single day" ----

def busiest(s: Summary) -> list[str]:
    if s.busiest_day < 20:
        return []
    return ["i'm fine.", "i'm fine. really.", "my keyboard remembers.", "don't ask.",
            "never again. (lie)", "deadline energy.", "it was a whole thing.", "that was a day.",
            "hydration: zero.", "worth it. probably.", "we don't talk about it.",
            "hold my beer.", "two red bull zeros deep.", "headphones on. music off.",
            "then one cold heineken."]


# ---- Under the facts: what I was drinking, from when the commits happened ----

def _when(key: str, s: Summary) -> tuple[str, str]:
    """How to say that coding day, for daytime and for nighttime."""
    today = (date.fromisoformat(s.yesterday) + timedelta(days=1)).isoformat()
    if key == today:
        return "today", "tonight"
    if key == s.yesterday:
        return "yesterday", "last night"
    day = date.fromisoformat(key).strftime("%A").lower()
    return day, f"{day} night"


def fuel(s: Summary) -> list[str]:
    if not s.fuel:
        return []
    out = []
    key, f = list(s.fuel.items())[-1]
    recent = (date.fromisoformat(s.yesterday) - date.fromisoformat(key)).days < 6
    day, night = _when(key, s)
    beer = f.brand
    if recent and f.weekend:
        out += [f"{day}: {beer}. no caffeine on weekends.", f"{day}: weekend, so {beer}. that's the rule.",
                f"{night}: {beer}, a few commits, no caffeine."]
    elif recent:
        if f.latte:
            out += [f"{day}: one iced venti latte. never two.",
                    f"{day}: on campus, iced latte in hand.",
                    f"{day}: venti latte. 3 long shots. 8 pumps.",
                    f"{day}: 4 vanilla, 4 caramel, all sugar free.",
                    f"{day}: iced venti sugar free vanilla protein latte.",
                    f"{day}: the usual. iced sf vanilla protein latte.",
                    "+4 sf caramel, +4 sf vanilla, 3 long shots. always."]
        if f.red_bulls == 2:
            out += [f"{night}: two red bull zeros. stuff got built.",
                    f"{night}: 2 red bull zeros, {f.night_commits} commits, from bed."]
        elif f.red_bulls:
            out += [f"{night}: red bull zero. building mode.",
                    f"{night}: red bull zero + {f.night_commits} commits from bed."]
        if f.beer == "done":
            out += [f"{night}: worked till it was done. then {beer}.",
                    f"{day}: finished it. caffeine out, {beer} in.",
                    f"{night}: shipped. cracked open a cold {beer}."]
        elif f.beer == "fixing":
            out += [f"{night}: bug fixes and a cold {beer}.",
                    f"{night}: {beer} night. fixing and maintaining.",
                    f"{night}: maintenance mode, {beer} in hand, in bed."]
    if (y := s.fuel.get(s.yesterday)) and y.commits:
        out += ["committed yesterday, so: gym.", "work done ahead of schedule. gym earned."]
    elif s.yesterday not in s.fuel:
        out += ["yesterday: laundry, meal prep, a new show.", "no commits yesterday. movie marathon.",
                "yesterday: friends, chores, zero code."]
    t = s.month_fuel
    if t.beers and (t.lattes or t.red_bulls):
        out += ["caffeine and beer: never at the same time.", "red bull zero = building. beer = fixing."]
    if t.lattes >= 3:
        out += [f"{t.lattes} venti lattes. 3 long shots each.",
                f"{t.lattes} iced sf vanilla protein lattes. same order every time.",
                f"{t.lattes} lattes = {8 * t.lattes} pumps of sugar free syrup."]
    return out


# ---- Under the commit clock, after the busiest hour ----

HOUR_QUIPS = [  # (from this hour on, quips)
    (0, ["who needs sleep", "sleep is a suggestion", "the bugs come out at night", "owl mode: on",
         "night shift, unpaid", "it's quiet. too quiet", "coding from bed",
         "red bull zero hours", "laptop in bed, headphones on"]),
    (5, ["up before the bugs", "early bird gets the merge", "before the coffee kicks in",
         "the world is quiet. good", "sunrise commits", "latte hasn't happened yet"]),
    (9, ["coffee-powered", "peak caffeine", "brain fully booted", "morning brain, best brain",
         "iced venti in hand", "on campus, 3 long shots in",
         "protein latte in hand"]),
    (13, ["like a normal person", "post-lunch focus", "office hours", "suspiciously reasonable",
          "a functioning adult, apparently", "on campus, latte in hand",
          "latte #1. also the last one"]),
    (18, ["after-dinner shift", "dinner, then deploy", "the second shift", "prime time",
          "evening debugging hours", "sunset. latte's worn off", "gym done. back to it"]),
    (22, ["sleep is a suggestion", "night owl hours", "one more commit, then bed",
          "bedtime is a social construct", "just one more fix", "in bed. laptop on lap",
          "one more commit, then heineken"]),
]


def hours(h: int) -> list[str]:
    quips = [q for start, q in HOUR_QUIPS if h >= start][-1]
    return [f"{hour(h)}. {q}." for q in quips]


# ---- Beside the "languages" heading ----

def languages(langs: list[tuple[str, int]]) -> list[str]:
    named = [(name, v) for name, v in langs if name != "Other"]
    if not named:
        return []
    top, share = named[0][0].lower(), named[0][1] / sum(v for _, v in langs)
    if share >= 0.5 and len(named) > 1:
        second = named[1][0].lower()
        return [f"mostly {top}. sorry, {second}.", f"{top} is doing the heavy lifting",
                f"{top} gang.", f"{round(100 * share)}% {top}. no regrets.",
                f"it's {top} all the way down", f"{second} is the side quest",
                f"{top} main, {second} alt", f"{top}, obviously.", "slowly moving it all to neovim"]
    if share >= 0.5:
        return [f"just {top}, really.", f"{top} and nothing else", f"loyal to {top}"]
    return ["a bit of everything.", "polyglot, allegedly.", "can't commit to just one. ironic.",
            "jack of all languages"]


# ---- Beside one of the other languages in the list ----

LANGUAGE_QUIPS = {
    "Python": ["pycharm. for now.", "indentation enjoyer", "import antigravity", "whitespace matters", "pip install everything"],
    "Java": ["intellij. for now.", "public static void quirky()", "AbstractQuipFactoryBean", "write once, debug everywhere",
             "verbose, but loyal"],
    "JavaScript": ["intellij, until neovim wins", "[] + {} = ?", "undefined is not a function", "it works. don't ask why.", "NaN !== NaN"],
    "TypeScript": ["intellij, until neovim wins", "javascript in a suit", "any, any, any", "types: mostly vibes"],
    "CSS": ["centered a div once", "!important", "looked fine locally"],
    "HTML": ["a programming language. fight me.", "<div><div><div>"],
    "Lua": ["it's my neovim config", "init.lua and friends", "for neovim. only neovim."],
    "C": ["segfault (core dumped)", "malloc and pray", "neovim, in wsl"],
    "C++": ["400-line template errors", "undefined behavior enjoyer"],
    "C#": ["java with better manners"],
    "Rust": ["fighting the borrow checker", "blazingly fast (tm)"],
    "Go": ["if err != nil", "gopher it"],
    "Shell": ["works on my machine", "chmod +x and hope"],
    "SQL": ["DROP TABLE regrets;", "SELECT * FROM problems"],
    "Kotlin": ["java, but fun"],
    "Swift": ["optional?.chaining?.everywhere"],
    "PHP": ["still runs the internet"],
    "Ruby": ["too pretty to be fast"],
    "R": ["statistically significant"],
    "Dockerfile": ["works in my container"],
    "Makefile": ["tabs, not spaces. or else."],
    "Haskell": ["a monad is just a..."],
    "Assembly": ["mov eax, 1 ; why"],
    "MATLAB": ["1-indexed and proud"],
    "Scala": ["java with a phd"],
    "TeX": ["\\begin{suffering}"],
}

SMALL_QUIPS = ["a phase.", "tried it once.", "one weekend, zero regrets", "it seemed like a good idea",
               "for science.", "a brief situationship"]


def language_row(name: str, share: float, hidden: int) -> list[str]:
    if name == "Other":
        out = ["the junk drawer", "side quests", "misc. regrets"]
        if hidden > 1:
            out += [f"{hidden} more languages in here", f"{hidden} phases, one row"]
        return out
    return LANGUAGE_QUIPS.get(name, []) + (SMALL_QUIPS if share < 0.02 else [])


# ---- Under the repositories ----

def repos(s: Summary) -> list[str]:
    out = ["naming things is still the hardest part", "every repo starts as 'just a quick script'",
           "readme coming soon (since forever)", "todo: finish the side projects",
           "started on campus, finished in bed", "the good ones ended with a heineken"]
    if s.top_repos and s.commits:
        top = s.top_repos[0]
        share = round(100 * top.commits / s.commits)
        if share >= 20:
            out.append(f"{share}% of my commits live in one repo.")
            if not top.private:
                out += [f"{top.label}: basically my second home", f"{share}% of my commits went into {top.label}"]
        if not top.private and top.deleted >= 1000:
            out.append(f"deleted {compact(top.deleted)} lines in {top.label}. no regrets.")
        hidden = sum(r.private for r in s.top_repos)
        if hidden:
            out += ["1 of these is private. trust me, it's great." if hidden == 1
                    else f"{hidden} of these are private. they're great, trust me.",
                    "the private ones are the good ones. allegedly."]
    if s.stars:
        out += [f"{s.stars} {plural(s.stars, 'star')}. hi mom.",
                f"{s.stars} {plural(s.stars, 'star')}. each one framed on my wall."]
    if s.forks:
        out.append(f"{s.forks} {plural(s.forks, 'fork')}. someone out there is using this.")
    if s.organizations:
        orgs = "1 org trusts" if s.organizations == 1 else f"{s.organizations} orgs trust"
        out.append(f"{orgs} me with write access. bold.")
    if s.owned_repos >= 2:
        out.append(f"{s.owned_repos} repos. naming them was the hard part.")
    if s.contributed_repos > s.owned_repos:
        out.append(f"committed to {s.contributed_repos} {plural(s.contributed_repos, 'repo')}. i get around.")
    return out


# ---- The printed footer ----

FOOTERS = [
    "recounted every night from raw git history. the green squares lie.",
    "counted from every branch of every repo, not just the green squares.",
    "recounted nightly from git log while i (supposedly) sleep.",
    "fresh from git log. merges, lockfiles and vendored code not invited.",
    "numbers straight from git history, recounted every night.",
    "recounted at 1am from git log. i'm probably still up.",
]
