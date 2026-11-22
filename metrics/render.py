"""Renders the summary as an SVG card, one file per color scheme."""

from __future__ import annotations

from html import escape

from .languages import color_of
from .stats import Summary

W, P = 840, 28  # canvas width, outer padding
CW = W - 2 * P  # content width

THEMES = {
    "light": dict(bg="#ffffff", border="#d1d9e0", fg="#1f2328", fg2="#59636e", fg3="#818b98",
                  rule="#d1d9e0", accent="#bc4c00", add="#1a7f37", delete="#cf222e", other="#c8d1da"),
    "dark": dict(bg="#0d1117", border="#30363d", fg="#f0f6fc", fg2="#9198a1", fg3="#6e7681",
                 rule="#30363d", accent="#f0883e", add="#3fb950", delete="#f85149", other="#3d444d"),
}

SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

FOOTER = "counted from raw git history, not the green squares"


def compact(n: int) -> str:
    """1,284 / 12.9K / 4.2M"""
    if n < 10_000:
        return f"{n:,}"
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div * 0.99995:
            v = n / div
            text = f"{v:.1f}" if v < 100 else f"{v:.0f}"
            return text.removesuffix(".0") + suffix
    return f"{n:,}"


def _pct(share: float) -> str:
    return "<0.1%" if share < 0.001 else f"{share * 100:.1f}%"


def _plural(n: int, word: str) -> str:
    return f"{word}{'' if n == 1 else 's'}"


def _hour(h: int) -> str:
    return {0: "midnight", 12: "noon"}.get(h) or f"{h % 12} {'am' if h < 12 else 'pm'}"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _text(x, y, content, cls, anchor=None, extra="") -> str:
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{a}{extra}>{content}</text>'


def _span(content, cls=None, dx=None) -> str:
    c = f' class="{cls}"' if cls else ""
    d = f' dx="{dx}"' if dx else ""
    return f"<tspan{c}{d}>{content}</tspan>"


def _dashed(y) -> str:
    return f'<line x1="{P}" y1="{y}.5" x2="{W - P}" y2="{y}.5" class="dash"/>'


def _column(x, y, w, h, r=2.0) -> str:
    """A column with rounded top corners and a square base."""
    r = min(r, w / 2, h)
    return (f"M{x:.2f},{y + h:.2f}V{y + r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + r:.2f},{y:.2f}"
            f"H{x + w - r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + w:.2f},{y + r:.2f}V{y + h:.2f}Z")


def _style(c: dict) -> str:
    return f"""
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
    .faint {{ fill: {c['fg3']}; }}
    .add {{ fill: {c['add']}; }}
    .del {{ fill: {c['delete']}; }}
    .hi {{ fill: {c['accent']}; }}
    .bar {{ fill: {c['accent']}; opacity: .45; }}
    .bar-hi {{ fill: {c['accent']}; }}
    .tick {{ fill: {c['rule']}; }}
    .dash {{ stroke: {c['rule']}; stroke-width: 1; stroke-dasharray: 3 4; shape-rendering: crispEdges; }}
    """


def _hero(s: Summary, out: list[str], y: int) -> int:
    """All-time totals, left column. Returns the bottom edge."""
    out.append(_text(P - 3, y + 62, f"{s.commits:,}", "hero"))
    out.append(_text(P, y + 88, f"{_plural(s.commits, 'commit')} since {s.since}", "lead"))
    lines = [
        _span(f"+{compact(s.added)}", "mono add") + _span(f"−{compact(s.deleted)}", "mono del", 8)
        + _span("lines", dx=8),
    ]
    if s.commits_this_year:
        lines.append(_span(f"{s.commits_this_year:,}", "em") + f" so far in {s.year}")
    if s.active_days:
        days = _span(f"{s.active_days:,}", "em") + f" {_plural(s.active_days, 'day')} with a commit"
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
        days = f"{m.active_days} of {m.today} {_plural(m.today, 'day')}"
        out.append(_text(x0, y + 50, f"{n:,}" + _span(f"{_plural(n, 'commit')} on {days}", "body", 8), "big"))
    else:
        out.append(_text(x0, y + 50, "nothing yet", "big"))

    top, plot_h = y + 72, 52
    base = top + plot_h
    slot = w / len(m.days)
    bw = slot - 4
    peak = max(m.days)
    for i, v in enumerate(m.days):
        x = x0 + i * slot + 2
        cx = x + bw / 2
        if i + 1 > m.today:
            out.append(f'<circle cx="{cx:.1f}" cy="{base - 1.5}" r="1.5" class="tick"/>')
        elif not v:
            out.append(f'<rect x="{x:.1f}" y="{base - 2}" width="{bw:.1f}" height="2" class="tick"/>')
        else:
            h = max(3.0, v / peak * plot_h)
            hi = i + 1 == m.best_day
            out.append(f'<path d="{_column(x, base - h, bw, h)}" class="{"bar-hi" if hi else "bar"}"/>')
            if hi:
                out.append(_text(cx, base - h - 6, f"{v}", "axis hi", "middle"))

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

    notes = []
    if n:
        notes.append(_span(f"+{compact(m.added)}", "mono add") + _span(f"−{compact(m.deleted)}", "mono del", 8)
                     + _span("lines this month", dx=8))
    if m.record:
        notes.append(_span("already my biggest month", "hi em"))
    elif m.previous:
        notes.append(f"{m.previous_name} had {m.previous:,}")
    if notes:
        joined = notes[0] + "".join(_span(t, dx=22) for t in notes[1:])
        out.append(_text(x0, base + 42, joined, "body"))
        return base + 42
    return base + 16


def _clock(s: Summary, out: list[str], y: int) -> None:
    """Commits by hour of day, right-aligned."""
    cw = 264
    x0 = W - P - cw
    peak_h = max(range(24), key=lambda h: s.hours[h])
    peak = s.hours[peak_h]
    out.append(_text(x0, y, "when I commit", "h"))
    out.append(_text(W - P, y, "mostly around " + _span(_hour(peak_h), "hi em"), "body", "end"))
    top, plot_h = y + 12, 30
    base = top + plot_h
    slot = cw / 24
    bw = slot - 3
    for h, v in enumerate(s.hours):
        x = x0 + h * slot + 1.5
        if not v:
            out.append(f'<rect x="{x:.1f}" y="{base - 2}" width="{bw:.1f}" height="2" class="tick"/>')
            continue
        bh = max(3.0, v / peak * plot_h)
        out.append(f'<path d="{_column(x, base - bh, bw, bh)}" class="{"bar-hi" if h == peak_h else "bar"}"/>')
    for h, label in ((0, "midnight"), (6, "6am"), (12, "noon"), (18, "6pm")):
        x = x0 + h * slot + 1.5
        out.append(_text(x, base + 15, label, "axis"))


def render(s: Summary, theme: str) -> str:
    c = THEMES[theme]
    out: list[str] = []
    esc = escape

    out.append(_text(P, 46, f'{esc(s.name)}' + _span(f"@{esc(s.login)}", "handle", 10), "title"))

    # Top: all-time totals beside the current month
    y = 70
    left_end = _hero(s, out, y)
    right_end = _this_month(s, out, P + 344, y)
    y = max(left_end, right_end) + 30
    out.append(_dashed(y))

    # Middle: pull requests and busiest day, beside the commit clock
    y += 36
    facts = []
    if s.pull_requests:
        merged = f", {_span(f'{s.merged_pull_requests:,}', 'em')} merged" if s.merged_pull_requests else ""
        facts.append(_span(f"{s.pull_requests:,}", "em") + f" {_plural(s.pull_requests, 'pull request')} opened{merged}")
    if s.busiest_day:
        facts.append(_span(f"{s.busiest_day:,}", "em")
                     + f" {_plural(s.busiest_day, 'commit')} in a single day ({s.busiest_date})")
    fy = y + 14 if len(facts) > 1 else y + 26
    for f in facts:
        out.append(_text(P, fy, f, "body"))
        fy += 24
    if any(s.hours):
        _clock(s, out, y)
    y += 56

    # Bottom: repositories (left) and languages (right)
    y += 44
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
        (s.stars, _plural(s.stars, "star")),
        (s.forks, _plural(s.forks, "fork")),
        (s.organizations, _plural(s.organizations, "org")),
    ) if v]
    if figures:
        left_end += 36
        parts = [_span(f"{compact(v)}", "em", 18 if i else None) + f" {label}" for i, (v, label) in enumerate(figures)]
        out.append(_text(lx, left_end, "".join(parts), "body"))

    if s.languages:
        out.append(_text(rx, y, "languages", "h"))
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
        ry += 36
        row_h = 26
        for (name, v), color in zip(s.languages, colors):
            out.append(f'<rect x="{rx:.1f}" y="{ry - 9}" width="8" height="8" rx="2" fill="{color}"/>')
            out.append(_text(rx + 18, ry, esc(name), "name"))
            out.append(_text(W - P - 60, ry, compact(v), "mono", "end"))
            out.append(_text(W - P, ry, _pct(v / total), "mono-strong", "end"))
            ry += row_h
        right_end = ry - row_h

    y = max(left_end, right_end) + 30
    out.append(_dashed(y))
    y += 24
    out.append(_text(P, y, FOOTER, "foot"))
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
