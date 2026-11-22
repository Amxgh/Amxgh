"""What I was drinking while I committed, worked out from when the commits happened.

The rules, straight from the source:

- Before sunset is day, after sunset is night. Commits in the small hours (before
  5am) belong to the night before.
- Weekends are caffeine-free: any commits on a Saturday or Sunday mean a beer.
- Any daytime commits on a weekday mean exactly one iced venti latte. Never two.
- A big night of building (lots of commits, mostly not fixes) means a Red Bull Zero,
  or two if there was no latte that day and the night ran long.
- A night of fixing and maintaining means a beer.
- A caffeinated day that runs straight on into the night and then stops means the
  work got finished, and gets a celebratory Heineken once the caffeine's done its job.
- Caffeine and beer are never mixed, so a Red Bull night with no finish line gets
  no beer.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NIGHT_ENDS = 5  # commits before 5am count towards the previous night
RED_BULL_NIGHT = 6  # night commits that make it a building night rather than a beer night
SECOND_RED_BULL = 15  # night commits (or LONG_NIGHT hours) for a second can
LONG_NIGHT = 5
CONTINUOUS = timedelta(hours=2)  # a longer gap across sunset means two separate sessions

BEERS = ["heineken", "heineken", "heineken", "hoegaarden", "dos equis"]  # mostly heineken

_FIX = re.compile(r"\b(?:bug|hot)?fix", re.IGNORECASE)


@dataclass
class Fuel:
    day: date
    weekend: bool
    day_commits: int = 0
    night_commits: int = 0
    night_fixes: int = 0
    latte: bool = False
    red_bulls: int = 0
    beer: str = ""  # "", "weekend", "fixing" or "done"
    times: list[datetime] = field(default_factory=list, repr=False)

    @property
    def brand(self) -> str:
        """Which beer it was: a Heineken, usually."""
        return BEERS[self.day.toordinal() % len(BEERS)] if self.beer else ""

    @property
    def commits(self) -> int:
        return self.day_commits + self.night_commits


@dataclass
class Tally:
    lattes: int = 0
    red_bulls: int = 0
    beers: int = 0

    def add(self, f: Fuel) -> None:
        self.lattes += f.latte
        self.red_bulls += f.red_bulls
        self.beers += bool(f.beer)


def sunset(d: date, lat: float, lon: float, tz: ZoneInfo) -> datetime:
    """Local sunset on that day (NOAA's approximation; good to a few minutes)."""
    g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl))
              - math.tan(phi) * math.tan(decl))
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    minutes = 720 - 4 * (lon - ha) - eqtime  # UTC minutes after midnight
    utc = datetime.combine(d, time(), ZoneInfo("UTC")) + timedelta(minutes=minutes)
    return utc.astimezone(tz)


def tally(days: dict[str, Fuel], prefix: str = "") -> Tally:
    t = Tally()
    for key, f in days.items():
        if key.startswith(prefix):
            t.add(f)
    return t


def fuel(commits, tz: ZoneInfo, location: tuple[float, float] | None) -> dict[str, Fuel]:
    """Each coding day's drinks, keyed by the day's ISO date."""
    days: dict[date, Fuel] = {}
    sunsets: dict[date, datetime] = {}

    def dusk(d: date) -> datetime:
        if d not in sunsets:
            sunsets[d] = (sunset(d, *location, tz) if location
                          else datetime.combine(d, time(18), tz))
        return sunsets[d]

    for c in commits:
        t = datetime.fromtimestamp(c.timestamp, tz)
        d = t.date() - timedelta(days=1) if t.hour < NIGHT_ENDS else t.date()
        f = days.get(d) or days.setdefault(d, Fuel(day=d, weekend=d.weekday() >= 5))
        f.times.append(t)
        if t.hour < NIGHT_ENDS or t >= dusk(d):
            f.night_commits += 1
            f.night_fixes += bool(_FIX.search(c.subject))
        else:
            f.day_commits += 1

    for d, f in days.items():
        f.times.sort()
        if f.weekend:
            f.beer = "weekend"
            continue
        f.latte = f.day_commits > 0
        if not f.night_commits:
            continue
        night = [t for t in f.times if t.hour < NIGHT_ENDS or t >= dusk(d)]
        before = [t for t in f.times if t not in night]
        building = f.night_commits >= RED_BULL_NIGHT and 2 * f.night_fixes < f.night_commits
        if building:
            long_night = night[-1] - night[0] >= timedelta(hours=LONG_NIGHT)
            f.red_bulls = 2 if not f.latte and (f.night_commits >= SECOND_RED_BULL or long_night) else 1
        if before and night[0] - before[-1] <= CONTINUOUS:
            f.beer = "done"  # worked straight through, then stopped: it's finished
        elif not building:
            f.beer = "fixing"
    return {d.isoformat(): f for d, f in sorted(days.items())}
