"""Renders the summary as an SVG card, one file per color scheme."""

from __future__ import annotations

from html import escape

from .languages import color_of
from .stats import Summary

W, P = 840, 24  # canvas width, outer padding
CW = W - 2 * P  # content width
GAP = 12

THEMES = {
    "light": dict(bg="#ffffff", border="#d1d9e0", tile="#f6f8fa", fg="#1f2328", fg2="#59636e",
                  fg3="#818b98", rule="#e6eaef", track="#eff2f5", accent="#0969da",
                  add="#1a7f37", delete="#cf222e", other="#c8d1da"),
    "dark": dict(bg="#0d1117", border="#30363d", tile="#151b23", fg="#f0f6fc", fg2="#9198a1",
                 fg3="#6e7681", rule="#21262d", track="#21262d", accent="#4493f8",
                 add="#3fb950", delete="#f85149", other="#3d444d"),
}

FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'

FOOTNOTE = ("Every branch of every repository, public and private · only commits I authored · "
            "no merges, lockfiles, vendored or generated files")


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


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _text(x, y, content, cls, anchor=None, extra="") -> str:
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}"{a}{extra}>{content}</text>'


def _column(x, y, w, h, r=4.0) -> str:
    """A column with rounded top corners and a square base."""
    r = min(r, w / 2, h)
    return (f"M{x:.2f},{y + h:.2f}V{y + r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + r:.2f},{y:.2f}"
            f"H{x + w - r:.2f}A{r:.2f},{r:.2f} 0 0 1 {x + w:.2f},{y + r:.2f}V{y + h:.2f}Z")


def _style(c: dict) -> str:
    return f"""
    text {{ font-family: {FONT}; fill: {c['fg']}; }}
    .title {{ font-size: 15px; font-weight: 600; }}
    .handle {{ font-size: 12px; font-weight: 400; fill: {c['fg2']}; }}
    .section {{ font-size: 10.5px; font-weight: 600; letter-spacing: .09em; fill: {c['fg2']}; }}
    .label {{ font-size: 11.5px; fill: {c['fg2']}; }}
    .faint {{ font-size: 11px; fill: {c['fg3']}; }}
    .axis-label {{ font-size: 10px; fill: {c['fg3']}; font-variant-numeric: tabular-nums; }}
    .value {{ font-size: 24px; font-weight: 600; letter-spacing: -.02em; }}
    .stat {{ font-size: 15px; font-weight: 600; }}
    .name {{ font-size: 12.5px; }}
    .num {{ font-size: 12px; fill: {c['fg2']}; font-variant-numeric: tabular-nums; }}
    .num-strong {{ font-size: 12px; font-variant-numeric: tabular-nums; }}
    .tile {{ fill: {c['tile']}; }}
    .rule {{ stroke: {c['rule']}; stroke-width: 1; shape-rendering: crispEdges; }}
    .track {{ fill: {c['track']}; }}
    .bar {{ fill: {c['accent']}; }}
    """


def render(s: Summary, theme: str) -> str:
    c = THEMES[theme]
    out: list[str] = []
    esc = escape

    # Header
    out.append(_text(P, 40, f'{esc(s.name)}<tspan class="handle" dx="8">@{esc(s.login)}</tspan>', "title"))
    out.append(_text(W - P, 40, f"Updated {s.updated}", "faint", "end"))

    # Activity: headline tiles
    y = 78
    out.append(_text(P, y, "ACTIVITY", "section"))
    out.append(_text(W - P, y, "All time · public and private", "faint", "end"))
    y += 12

    def last_year(n: int) -> str:
        return f"{compact(n)} in the last year" if n else ""

    streak = f"Longest streak {s.longest_streak} day{'s' if s.longest_streak != 1 else ''}"
    tiles = [
        ("Commits", s.commits, last_year(s.commits_year), None),
        ("Lines added", s.added, last_year(s.added_year), c["add"]),
        ("Lines deleted", s.deleted, last_year(s.deleted_year), c["delete"]),
        ("Active days", s.active_days, streak if s.longest_streak > 1 else "", None),
    ]
    tiles = [t for t in tiles if t[1]]
    if tiles:
        tw = (CW - GAP * (len(tiles) - 1)) / len(tiles)
        for i, (label, value, caption, dot) in enumerate(tiles):
            x = P + i * (tw + GAP)
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="78" rx="10" class="tile"/>')
            lx = x + 16
            if dot:
                out.append(f'<circle cx="{x + 19.5:.1f}" cy="{y + 18.5}" r="3.5" fill="{dot}"/>')
                lx = x + 29
            out.append(_text(lx, y + 23, label, "label"))
            out.append(_text(x + 16, y + 52, compact(value), "value"))
            if caption:
                out.append(_text(x + 16, y + 69, esc(caption), "faint"))
        y += 78

    # Activity: secondary figures
    cells = [(v, label) for v, label in (
        (s.pull_requests, "Pull requests"),
        (s.merged_pull_requests, "Merged"),
        (s.reviews, "Code reviews"),
        (s.issues, "Issues"),
        (s.busiest_day, "Most commits in a day"),
    ) if v]
    if cells:
        y += 18
        cw = CW / len(cells)
        for i, (value, label) in enumerate(cells):
            x = P + i * cw
            if i:
                out.append(f'<line x1="{x:.0f}.5" y1="{y + 2}" x2="{x:.0f}.5" y2="{y + 36}" class="rule"/>')
            out.append(_text(x + 16, y + 16, compact(value), "stat"))
            out.append(_text(x + 16, y + 33, label, "label"))
        y += 38

    # Activity: commits per month
    months = s.monthly
    peak = max((v for _, v in months), default=0)
    if peak:
        y += 34
        out.append(_text(P, y, "Commits per month", "label"))
        plot_top, plot_h = y + 26, 64
        base = plot_top + plot_h
        slot = CW / len(months)
        bw = max(1.0, min(24.0, slot - 2))
        peak_i = max(range(len(months)), key=lambda i: (months[i][1], i))
        for i, (_, v) in enumerate(months):
            if not v:
                continue
            h = max(2.0, v / peak * plot_h)
            x = P + i * slot + (slot - bw) / 2
            out.append(f'<path d="{_column(x, base - h, bw, h)}" class="bar"/>')
        out.append(f'<line x1="{P}" y1="{base}.5" x2="{W - P}" y2="{base}.5" class="rule"/>')
        # year ticks at each January (and the first month, if there's room before the next one)
        ticks = [i for i, (m, _) in enumerate(months) if m.endswith("-01")]
        if not ticks or ticks[0] * slot > 34:
            ticks.insert(0, 0)
        for i in ticks:
            out.append(_text(P + i * slot + (slot - bw) / 2, base + 16, months[i][0][:4], "axis-label"))
        # label the peak month
        px = P + peak_i * slot + slot / 2
        anchor = "start" if px < P + 50 else "end" if px > W - P - 50 else "middle"
        if anchor != "middle":
            px += -(bw / 2) if anchor == "start" else bw / 2
        month = _month_name(months[peak_i][0])
        out.append(_text(px, plot_top - 7, f"{peak:,} in {month}", "axis-label", anchor))
        y = base + 16

    # Bottom: repositories (left) and languages (right)
    y += 42
    col_w = (CW - 32) / 2
    lx, rx = P, P + col_w + 32
    out.append(_text(lx, y, "REPOSITORIES", "section"))
    left_end = right_end = y

    figures = [(v, label) for v, label in (
        (s.owned_repos, "Owned"),
        (s.contributed_repos, "Contributed"),
        (s.stars, "Stars"),
        (s.forks, "Forks"),
        (s.organizations, "Orgs"),
    ) if v]
    ly = y + 14
    if figures:
        fw = col_w / len(figures)
        for i, (value, label) in enumerate(figures):
            out.append(_text(lx + i * fw, ly + 18, compact(value), "stat"))
            out.append(_text(lx + i * fw, ly + 35, label, "label"))
        ly += 62

    if s.top_repos:
        c_del, c_add, c_com = lx + col_w, lx + col_w - 58, lx + col_w - 116
        out.append(_text(lx, ly, "Most active", "faint"))
        for x, head in ((c_com, "Commits"), (c_add, "Added"), (c_del, "Deleted")):
            out.append(_text(x, ly, head, "faint", "end"))
        ly += 10
        for i, r in enumerate(s.top_repos):
            star = f"  ★ {compact(r.stars)}" if r.stars else ""
            name = esc(_truncate(r.label, 27 - len(star)))
            star_span = f'<tspan class="faint">{star}</tspan>' if star else ""
            out.append(_text(lx, ly + 16, name + star_span, "name"))
            out.append(_text(c_com, ly + 16, f"{r.commits:,}", "num-strong", "end"))
            out.append(_text(c_add, ly + 16, f"+{compact(r.added)}" if r.added else "–", "num", "end"))
            out.append(_text(c_del, ly + 16, f"−{compact(r.deleted)}" if r.deleted else "–", "num", "end"))
            out.append(f'<rect x="{lx}" y="{ly + 23}" width="{col_w:.1f}" height="3" rx="1.5" class="track"/>')
            fill_w = max(3.0, col_w * r.commits / s.commits)  # share of all my commits
            out.append(f'<rect x="{lx}" y="{ly + 23}" width="{fill_w:.1f}" height="3" rx="1.5" class="bar"/>')
            ly += 32
    left_end = ly

    if s.languages:
        out.append(_text(rx, y, "LANGUAGES", "section"))
        count = f" · {s.language_count} languages" if s.language_count > 1 else ""
        out.append(_text(W - P, y, f"By lines I wrote{count}", "faint", "end"))
        ry = y + 16
        total = sum(v for _, v in s.languages)
        colors = [c["other"] if name == "Other" else _visible(color_of(name), theme) for name, _ in s.languages]
        out.append(f'<clipPath id="lang-bar"><rect x="{rx:.1f}" y="{ry}" width="{col_w:.1f}" height="8" rx="4"/></clipPath>')
        out.append('<g clip-path="url(#lang-bar)">')
        usable = col_w - 2 * (len(s.languages) - 1)
        x = rx
        for (name, v), color in zip(s.languages, colors):
            w = max(1.0, usable * v / total)
            out.append(f'<rect x="{x:.2f}" y="{ry}" width="{w:.2f}" height="8" fill="{color}"/>')
            x += w + 2
        out.append("</g>")
        ry += 34
        row_h = 26
        for i, ((name, v), color) in enumerate(zip(s.languages, colors)):
            out.append(f'<circle cx="{rx + 4:.1f}" cy="{ry - 4}" r="4" fill="{color}"/>')
            out.append(_text(rx + 16, ry, esc(name), "name"))
            out.append(_text(W - P - 58, ry, f"{compact(v)} lines", "num", "end"))
            out.append(_text(W - P, ry, _pct(v / total), "num-strong", "end"))
            ry += row_h
        right_end = ry - row_h + 8

    y = max(left_end, right_end) + 26
    out.append(f'<line x1="{P}" y1="{y}.5" x2="{W - P}" y2="{y}.5" class="rule"/>')
    y += 22
    out.append(_text(P, y, esc(FOOTNOTE), "faint"))
    h = y + 22

    title = f"{esc(s.name)}'s GitHub activity"
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'role="img" aria-label="{title}">',
        f"<title>{title}</title>",
        f"<style>{_style(c)}</style>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
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


def _month_name(key: str) -> str:
    y, m = key.split("-")
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{names[int(m) - 1]} {y}"
