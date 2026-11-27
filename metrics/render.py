"""Renders the summary as an SVG card, one file per color scheme.

The numbers are printed; the commentary is scribbled on top in a handwriting font,
with pen arrows and circles. What the scribbles say lives in scribbles.toml (read by
notes.py); this module decides where they go, skipping any line that wouldn't fit.
"""

from __future__ import annotations

import base64
import json
import math
import random
from functools import cache
from html import escape
from pathlib import Path

from . import notes
from .fmt import compact, plural
from .languages import color_of
from .stats import Summary

W, P = 840, 28  # canvas width, outer padding
CW = W - 2 * P  # content width
RIGHT = P + 380  # left edge of this month's column

THEMES = {
    "light": dict(bg="#ffffff", border="#d1d9e0", fg="#1f2328", fg2="#59636e", fg3="#818b98",
                  rule="#d1d9e0", accent="#0a6fb0", add="#1a7f37", delete="#cf222e", other="#c8d1da",
                  ink="#6a4ff0"),
    "dark": dict(bg="#0d1117", border="#30363d", fg="#f0f6fc", fg2="#9198a1", fg3="#6e7681",
                 rule="#30363d", accent="#3fa9f5", add="#3fb950", delete="#f85149", other="#3d444d",
                 ink="#8369ff"),
}

SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'
HAND = '"Pen", "Segoe Print", "Bradley Hand", cursive'
HAND_PX = 22
FONT_FILE = Path(__file__).with_name("fonts") / "nanum-pen-script.woff2"  # SIL OFL, see fonts/OFL.txt
HAND_WIDTHS = json.loads(FONT_FILE.with_suffix(".widths.json").read_text())  # advance per char, in em


# ---- Text helpers -------------------------------------------------------------------

def _pct(share: float) -> str:
    return "<0.1%" if share < 0.001 else f"{share * 100:.1f}%"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _hand_width(text: str) -> float:
    """Rendered width of handwritten text, from the font's own glyph widths."""
    return HAND_PX * sum(HAND_WIDTHS.get(ch, 0.45) for ch in text)


# Printed text uses whatever system font the viewer has, so these are generous averages.
def _sans_width(text: str) -> float:  # 13px sans
    return len(text) * 6.4


def _mono_width(text: str) -> float:  # 12px mono
    return len(text) * 7.3


def _text(x, y, content, cls, anchor=None, extra="") -> str:
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{a}{extra}>{content}</text>'


def _span(content, cls=None, dx=None) -> str:
    c = f' class="{cls}"' if cls else ""
    d = f' dx="{dx}"' if dx else ""
    return f"<tspan{c}{d}>{content}</tspan>"


def _scribble(note: str | None, dx=10) -> str:
    """A handwritten aside that continues a printed line."""
    return _span(escape(note), "hand", dx) if note else ""


def _hand(x, y, note, anchor=None, tilt=0.0) -> str:
    t = _text(x, y, escape(note), "hand", anchor)
    return f'<g transform="rotate({tilt:.2f} {x:.1f} {y:.1f})">{t}</g>' if tilt else t


def _tilt(slot: str, around: float, spread: float) -> float:
    """A slightly different angle every run, like notes jotted at different times."""
    return around + random.Random(f"tilt-{slot}-{notes.RUN}").uniform(-spread, spread)


# ---- Pen strokes --------------------------------------------------------------------

def _rng(slot: str) -> random.Random:
    return random.Random(f"{slot}-{notes.RUN}")


def _smooth(pts: list[tuple[float, float]]) -> str:
    """A Catmull-Rom curve through the points, as path data."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def _pencil_line(y: float, slot: str) -> str:
    """A divider ruled by hand: not quite straight, not quite level."""
    rng = _rng(slot)
    n = 8
    pts = [(P + CW * i / n + (rng.uniform(-8, 8) if 0 < i < n else 0), y + rng.uniform(-1.0, 1.0))
           for i in range(n + 1)]
    return f'<path d="{_smooth(pts)}" class="pencil"/>'


def _arrow(x1, y1, x2, y2, bend: float, slot: str) -> str:
    """A curved pen arrow from (x1, y1) to (x2, y2); bend bows it sideways."""
    rng = _rng(slot)
    bend *= rng.uniform(0.6, 1.4)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    cx = (x1 + x2) / 2 - dy / length * bend
    cy = (y1 + y2) / 2 + dx / length * bend
    angle = math.atan2(y2 - cy, x2 - cx)
    head = min(7.5, length * 0.45)
    wings = []
    for spread in (-0.5, 0.45):
        a = angle + math.pi + spread + rng.uniform(-0.15, 0.15)
        wings.append((x2 + head * math.cos(a), y2 + head * math.sin(a)))
    (ax, ay), (bx, by) = wings
    return (f'<path d="M{x1:.1f},{y1:.1f} Q{cx:.1f},{cy:.1f} {x2:.1f},{y2:.1f} '
            f'M{ax:.1f},{ay:.1f} L{x2:.1f},{y2:.1f} L{bx:.1f},{by:.1f}" class="ink"/>')


def _loop(cx, cy, rx, ry, slot: str) -> str:
    """A quick circle around something: overshoots, drifts outward, slightly tilted."""
    rng = _rng(slot)
    tilt = rng.uniform(-0.2, 0.2)
    start = rng.uniform(-2.4, -1.0)
    turns = rng.uniform(1.08, 1.22)
    pts = []
    n = 26
    for i in range(n + 1):
        t = start + 2 * math.pi * turns * i / n
        grow = 1 + 0.14 * i / n + rng.uniform(-0.03, 0.03)
        x, y = rx * grow * math.cos(t), ry * grow * math.sin(t)
        pts.append((cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt)))
    return f'<path d="{_smooth(pts)}" class="ink"/>'


def _column(x, y, w, h, r=2.0) -> str:
    """A column with rounded top corners and a square base."""
    r = min(r, w / 2, h)
    return (f"M{x:.2f},{y + h:.2f}V{y + r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + r:.2f},{y:.2f}"
            f"H{x + w - r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + w:.2f},{y + r:.2f}V{y + h:.2f}Z")


@cache
def _font() -> str:
    if not FONT_FILE.exists():
        return ""
    data = base64.b64encode(FONT_FILE.read_bytes()).decode()
    return f'@font-face {{ font-family: "Pen"; src: url(data:font/woff2;base64,{data}) format("woff2"); }}'


def _style(c: dict) -> str:
    return f"""
    {_font()}
    text {{ font-family: {SANS}; fill: {c['fg']}; }}
    .title {{ font-size: 17px; font-weight: 600; }}
    .handle {{ font-family: {MONO}; font-size: 12px; font-weight: 400; fill: {c['fg2']}; }}
    .hero {{ font-size: 58px; font-weight: 700; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }}
    .big {{ font-size: 30px; font-weight: 700; letter-spacing: -.03em; font-variant-numeric: tabular-nums; }}
    .lead {{ font-size: 15px; fill: {c['fg2']}; }}
    .body {{ font-size: 13px; font-weight: 400; letter-spacing: 0; fill: {c['fg2']}; }}
    .em {{ font-weight: 600; fill: {c['fg']}; }}
    .h {{ font-family: {MONO}; font-size: 11.5px; fill: {c['fg2']}; }}
    .mono {{ font-family: {MONO}; font-size: 12px; fill: {c['fg2']}; font-variant-numeric: tabular-nums; }}
    .mono-strong {{ font-family: {MONO}; font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }}
    .axis {{ font-family: {MONO}; font-size: 10px; fill: {c['fg3']}; }}
    .foot {{ font-family: {MONO}; font-size: 11px; fill: {c['fg3']}; }}
    .name {{ font-size: 13px; }}
    .hand {{ font-family: {HAND}; font-size: {HAND_PX}px; font-weight: 400; letter-spacing: 0; fill: {c['ink']}; }}
    .ink {{ fill: none; stroke: {c['ink']}; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }}
    .pencil {{ fill: none; stroke: {c['rule']}; stroke-width: 1.2; stroke-linecap: round; }}
    .faint {{ fill: {c['fg3']}; }}
    .add {{ fill: {c['add']}; }}
    .del {{ fill: {c['delete']}; }}
    .hi {{ fill: {c['accent']}; }}
    .bar {{ fill: {c['accent']}; opacity: .45; }}
    .bar-hi {{ fill: {c['accent']}; }}
    .tick {{ fill: {c['rule']}; }}
    """


# ---- Sections -----------------------------------------------------------------------

def _hero(s: Summary, out: list[str], y: int) -> int:
    """All-time totals, left column. Returns the bottom edge."""
    number = f"{s.commits:,}"
    lead = f"{plural(s.commits, 'commit')} since {s.since}"
    out.append(_text(P - 3, y + 62, number, "hero"))
    out.append(_text(P, y + 88, lead, "lead"))

    number_w = 31 * sum(ch.isdigit() for ch in number) + 15 * number.count(",")
    nx, ny = P + number_w + 34, y + 30
    room = RIGHT - nx - 12

    def fits(lines: tuple[str, ...]) -> bool:
        return all(_hand_width(line) <= room - 8 * i for i, line in enumerate(lines))

    if note := notes.pick("hero", notes.hero(s), fits):
        lines = "".join(_text(nx + 8 * i, ny + 22 * i, escape(line), "hand") for i, line in enumerate(note))
        out.append(f'<g transform="rotate({_tilt("hero", -4, 1.5):.2f} {nx:.1f} {ny})">{lines}</g>')
        lead_end = P + len(lead) * 7.3
        out.append(_arrow(nx + 16, ny + 9 + 22 * (len(note) - 1), lead_end + 9, y + 82, -10, "hero"))

    lines = [
        _span(f"+{compact(s.added)}", "mono add") + _span(f"−{compact(s.deleted)}", "mono del", 8)
        + _span("lines", dx=8),
    ]
    if s.commits_this_year:
        lines.append(_span(f"{s.commits_this_year:,}", "em") + f" so far in {s.year}")
    if s.active_days:
        days = _span(f"{s.active_days:,}", "em") + f" {plural(s.active_days, 'day')} with a commit"
        if s.longest_streak > 1:
            days += f", {s.longest_streak} in a row at best"
        lines.append(days)
    ly = y + 124
    for line in lines:
        out.append(_text(P, ly, line, "body"))
        ly += 22
    return ly - 22


def _this_month(s: Summary, out: list[str], x0: float, y: int) -> int:
    """The current month day by day, right column. Returns the bottom edge."""
    m = s.month
    w = W - P - x0
    out.append(_text(x0, y + 14, f"{m.name.lower()} so far", "h"))
    n = m.commits
    if n:
        days = f"{m.active_days} of {m.today} {plural(m.today, 'day')}"
        out.append(_text(x0, y + 50, f"{n:,}" + _span(f"{plural(n, 'commit')} on {days}", "body", 8), "big"))
    else:
        out.append(_text(x0, y + 50, "nothing yet", "big"))

    top, plot_h = y + 72, 52
    base = top + plot_h
    slot = w / len(m.days)
    bw = slot - 4
    peak = max(m.days)
    heights = [v / peak * plot_h if peak else 0 for v in m.days]
    for i, v in enumerate(m.days):
        x = x0 + i * slot + 2
        if i + 1 > m.today:
            out.append(f'<circle cx="{x + bw / 2:.1f}" cy="{base - 1.5}" r="1.5" class="tick"/>')
        elif not v:
            out.append(f'<rect x="{x:.1f}" y="{base - 2}" width="{bw:.1f}" height="2" class="tick"/>')
        else:
            h = max(3.0, heights[i])
            hi = i + 1 == m.best_day
            out.append(f'<path d="{_column(x, base - h, bw, h)}" class="{"bar-hi" if hi else "bar"}"/>')
            if hi:
                out.append(_text(x + bw / 2, base - h - 6, f"{v}", "axis hi", "middle"))

    # a note beside the best day, if it stands out and there's room on either side of it
    if n and peak >= 5 and peak >= 2 * n / m.active_days:
        bx = x0 + (m.best_day - 1) * slot + 2
        nb = top + 15

        def clear(lo: float, hi: float) -> bool:
            return lo >= x0 and hi <= x0 + w and all(
                h < plot_h - 20 for j, h in enumerate(heights)
                if x0 + (j + 1) * slot > lo and x0 + j * slot < hi)

        for note in notes.ordered("best-day", notes.best_day(m, s)):
            nw = _hand_width(note)
            if clear(bx + bw + 22, bx + bw + 22 + nw):
                out.append(_hand(bx + bw + 22, nb, note))
                out.append(_arrow(bx + bw + 18, nb - 6, bx + bw + 4, top + 4, 3, "best"))
                break
            if clear(bx - 22 - nw, bx - 22):
                out.append(_hand(bx - 22, nb, note, "end"))
                out.append(_arrow(bx - 18, nb - 6, bx - 4, top + 4, -3, "best"))
                break

    def at(day: int) -> float:
        return x0 + (day - 1) * slot + slot / 2

    out.append(_text(x0 + 2, base + 16, "1", "axis"))
    last = len(m.days)
    if m.today < last - 2:
        out.append(_text(x0 + w - 2, base + 16, str(last), "axis", "end"))
    if m.today > 2:
        anchor = "end" if m.today >= last - 2 else "middle"
        tx = x0 + w - 2 if anchor == "end" else at(m.today)
        out.append(_text(tx, base + 16, "today", "axis hi", anchor))

    end = base + 16
    if n:
        end = base + 42
        out.append(_text(x0, end, _span(f"+{compact(m.added)}", "mono add")
                         + _span(f"−{compact(m.deleted)}", "mono del", 8) + _span("lines this month", dx=8), "body"))
    if note := notes.pick("month", notes.month(m), lambda t: _hand_width(t) <= w - 8):
        end += 28
        out.append(_hand(x0 + 4, end, note, tilt=_tilt("month", -1.5, 1.2)))
    return end


CLOCK_W = 264


def _clock(s: Summary, out: list[str], y: int) -> int:
    """Commits by hour of day, right-aligned. Returns the bottom edge."""
    x0 = W - P - CLOCK_W
    peak_h = max(range(24), key=lambda h: s.hours[h])
    peak = s.hours[peak_h]
    out.append(_text(x0, y, "when I commit", "h"))
    top, plot_h = y + 18, 30
    base = top + plot_h
    slot = CLOCK_W / 24
    bw = slot - 3
    for h, v in enumerate(s.hours):
        x = x0 + h * slot + 1.5
        if not v:
            out.append(f'<rect x="{x:.1f}" y="{base - 2}" width="{bw:.1f}" height="2" class="tick"/>')
            continue
        bh = max(3.0, v / peak * plot_h)
        out.append(f'<path d="{_column(x, base - bh, bw, bh)}" class="{"bar-hi" if h == peak_h else "bar"}"/>')

    px = x0 + peak_h * slot + slot / 2
    out.append(_loop(px, top + plot_h / 2, bw / 2 + 6, plot_h / 2 + 5, "clock"))
    for h, label in ((0, "midnight"), (6, "6am"), (12, "noon"), (18, "6pm")):
        span = math.ceil(len(label) * 6 / slot)
        if h - 1 <= peak_h <= h + span:  # the arrow comes up through here
            continue
        out.append(_text(x0 + h * slot + 1.5, base + 15, label, "axis"))

    note = notes.pick("hours", notes.hours(peak_h), lambda t: _hand_width(t) <= CLOCK_W)
    if not note:
        return base + 15
    nw = _hand_width(note)
    nx = min(max(px - nw * 0.6, x0), W - P - nw)
    ny = base + 46
    sx = min(max(px - 16, nx + 8), nx + nw - 8)
    out.append(_hand(nx, ny, note))
    out.append(_arrow(sx, ny - 17, px + 1, base + 13, 5, "clock-arrow"))
    return ny


def render(s: Summary, theme: str) -> str:
    c = THEMES[theme]
    out: list[str] = []
    esc = escape

    out.append(_text(P, 46, f'{esc(s.name)}' + _span(f"@{esc(s.login)}", "handle", 10), "title"))

    # Top: all-time totals beside the current month
    y = 70
    left_end = _hero(s, out, y)
    right_end = _this_month(s, out, RIGHT, y)
    y = max(left_end, right_end) + 28
    out.append(_pencil_line(y, "top"))

    # Middle: pull requests and busiest day, beside the commit clock
    y += 36
    clock = any(s.hours)
    room_end = (W - P - CLOCK_W - 24) if clock else W - P

    def aside(slot: str, printed: str, pool: list[str]) -> str:
        start = P + _sans_width(printed) + 10
        return _scribble(notes.pick(slot, pool, lambda t: start + _hand_width(t) <= room_end))

    facts = []
    if pr := s.pull_requests:
        merged = s.merged_pull_requests
        tail = f" {plural(pr, 'pull request')} opened"
        printed = f"{pr:,}{tail}" + (f", {merged:,} merged" if merged else "")
        line = _span(f"{pr:,}", "em") + tail + (f", {_span(f'{merged:,}', 'em')} merged" if merged else "")
        facts.append(line + aside("pull-requests", printed, notes.pull_requests(s)))
    if busiest := s.busiest_day:
        tail = f" {plural(busiest, 'commit')} in a single day ({s.busiest_date})"
        line = _span(f"{busiest:,}", "em") + tail
        facts.append(line + aside("busiest", f"{busiest:,}{tail}", notes.busiest(s)))
    t = s.month_fuel
    drinks = [(n, word) for n, word in ((t.lattes, "latte"), (t.red_bulls, "red bull zero"),
                                        (t.beers, "beer")) if n] if s.show_fuel else []
    if drinks:
        facts.append(", ".join(_span(f"{n:,}", "em") + f" {plural(n, word)}" for n, word in drinks)
                     + " this month")
    fy = y + 14 if len(facts) > 1 else y + 26
    for f in facts:
        out.append(_text(P, fy, f, "body"))
        fy += 24
    bottom = fy - 24
    fuel_notes = notes.fuel(s) if s.show_fuel else []
    if note := notes.pick("fuel", fuel_notes, lambda t: _hand_width(t) <= room_end - P - 12):
        bottom += 30
        out.append(_hand(P + 6, bottom, note, tilt=_tilt("fuel", -1.2, 1.0)))
    if clock:
        bottom = max(bottom, _clock(s, out, y))

    # Bottom: repositories (left) and languages (right)
    y = bottom + 46
    col_w = (CW - 44) / 2
    lx, rx = P, P + col_w + 44
    left_end = right_end = y

    if s.top_repos:
        c_com = lx + col_w - 112
        out.append(_text(lx, y, "most active repos", "h"))
        out.append(_text(c_com, y, "commits", "axis", "end"))
        out.append(_text(lx + col_w, y, "lines", "axis", "end"))
        ly = y + 28
        for r in s.top_repos:
            star = f"  ★ {compact(r.stars)}" if r.stars else ""
            name = esc(_truncate(r.label, 30 - len(star))) + (_span(star, "faint") if star else "")
            out.append(_text(lx, ly, name, "name"))
            out.append(_text(c_com, ly, f"{r.commits:,}", "mono-strong", "end"))
            added = f"+{compact(r.added)}" if r.added else "+0"
            deleted = f"−{compact(r.deleted)}" if r.deleted else "−0"
            out.append(_text(lx + col_w, ly, _span(added, "add") + _span(deleted, "del", 6), "mono", "end"))
            ly += 30
        left_end = ly - 30

    figures = [(v, label) for v, label in (
        (s.owned_repos, "of my own"),
        (s.contributed_repos, "committed to"),
        (s.stars, plural(s.stars, "star")),
        (s.forks, plural(s.forks, "fork")),
        (s.organizations, plural(s.organizations, "org")),
    ) if v]
    if figures:
        left_end += 36
        parts = [_span(f"{compact(v)}", "em", 18 if i else None) + f" {label}" for i, (v, label) in enumerate(figures)]
        out.append(_text(lx, left_end, "".join(parts), "body"))

    if s.top_repos or figures:
        if note := notes.pick("repos", notes.repos(s), lambda t: _hand_width(t) <= col_w - 14):
            left_end += 34
            out.append(_hand(lx + 6, left_end, note, tilt=_tilt("repos", -1.8, 1.2)))

    if s.languages:
        heading_room = col_w - _mono_width("languages") - 12
        heading_note = notes.pick("languages", notes.languages(s.languages),
                                  lambda t: _hand_width(t) <= heading_room)
        out.append(_text(rx, y, "languages" + _scribble(heading_note, 12), "h"))
        ry = y + 14
        total = sum(v for _, v in s.languages)
        colors = [c["other"] if name == "Other" else _visible(color_of(name), theme) for name, _ in s.languages]
        out.append(f'<clipPath id="lang-bar"><rect x="{rx:.1f}" y="{ry}" width="{col_w:.1f}" height="8" rx="2"/></clipPath>')
        out.append('<g clip-path="url(#lang-bar)">')
        usable = col_w - 2 * (len(s.languages) - 1)
        x = rx
        for (name, v), color in zip(s.languages, colors):
            w = max(1.0, usable * v / total)
            out.append(f'<rect x="{x:.2f}" y="{ry}" width="{w:.2f}" height="8" fill="{color}"/>')
            x += w + 2
        out.append("</g>")

        # one of the other languages gets a note of its own, between its name and its numbers
        named = sum(1 for name, _ in s.languages if name != "Other")
        candidates = []
        for name, v in s.languages[1:]:
            start = rx + 18 + _sans_width(name) + 10
            room = (W - P - 60 - _mono_width(compact(v)) - 16) - start
            pool = [q for q in notes.language_row(name, v / total, s.language_count - named)
                    if _hand_width(q) <= room]
            if pool:
                candidates.append((name, pool))
        row_note = {}
        if chosen := notes.pick("language-row", candidates):
            row_note[chosen[0]] = notes.pick(f"language-row-{chosen[0]}", chosen[1])

        ry += 36
        row_h = 26
        for (name, v), color in zip(s.languages, colors):
            out.append(f'<rect x="{rx:.1f}" y="{ry - 9}" width="8" height="8" rx="2" fill="{color}"/>')
            out.append(_text(rx + 18, ry, esc(name) + _scribble(row_note.get(name)), "name"))
            out.append(_text(W - P - 60, ry, compact(v), "mono", "end"))
            out.append(_text(W - P, ry, esc(_pct(v / total)), "mono-strong", "end"))
            ry += row_h
        right_end = ry - row_h

    y = max(left_end, right_end) + 30
    out.append(_pencil_line(y, "bottom"))
    y += 24
    out.append(_text(P, y, esc(notes.pick("footer", notes.footer()) or ""), "foot"))
    out.append(_text(W - P, y, f"updated {s.updated}", "foot", "end"))
    h = y + 22

    title = f"{esc(s.name)}'s GitHub activity"
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'role="img" aria-label="{title}">',
        f"<title>{title}</title>",
        f"<style>{_style(c)}</style>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="6" fill="{c["bg"]}" stroke="{c["border"]}"/>',
        *out,
        "</svg>",
    ]) + "\n"


def _visible(color: str, theme: str) -> str:
    """Lift near-black language colors (Lua, PowerShell, ...) so they read on a dark card."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    if theme != "dark" or 0.2126 * r + 0.7152 * g + 0.0722 * b > 70:
        return color
    r, g, b = (round(v + (255 - v) * 0.45) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"
