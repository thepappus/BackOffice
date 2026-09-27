"""Japanese business day calendar and the day/night session trade-date rule.

This module is foundational and deliberately first: every date in every
downstream calculation depends on it. The subtlety that catches people is the
night session — a derivatives trade executed on a Monday evening belongs to
Tuesday's trading day, so its trade date, its mark-to-market and its position
reporting all fall on Tuesday.

National holidays are computed from the Holiday Act rules (fixed dates, Happy
Monday dates, equinoxes, substitute holidays and citizens' holidays). The
equinox dates use the standard astronomical approximation, which is reliable for
1980-2099 but is an approximation; `HOLIDAY_OVERRIDES` exists for one-off
closures and for correcting any year where the approximation is disputed.

Exchange closure is a superset of national holidays: TSE and OSE are also closed
1-3 January and 31 December.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from functools import lru_cache

MONDAY = 0
SUNDAY = 6


class Session(str, Enum):
    """Derivatives trading sessions on OSE.

    DAY runs during the daytime of its own trading day. NIGHT begins on the
    evening of the *previous* calendar day and belongs to this trading day.
    """

    DAY = "day"
    NIGHT = "night"


# One-off additions to, or corrections of, the computed holiday set.
# Keyed by date, value is the reason (for auditability).
HOLIDAY_OVERRIDES: dict[date, str] = {
    # 2019 imperial transition: enthronement day and the two days bracketed by
    # it became holidays, giving a ten-day Golden Week.
    date(2019, 4, 30): "Citizens' holiday (imperial transition)",
    date(2019, 5, 1): "Enthronement of the Emperor",
    date(2019, 5, 2): "Citizens' holiday (imperial transition)",
    date(2019, 10, 22): "Enthronement ceremony",
    # 2020/2021 Olympic and Paralympic holiday moves.
    date(2020, 7, 23): "Marine Day (moved for Tokyo 2020)",
    date(2020, 7, 24): "Sports Day (moved for Tokyo 2020)",
    date(2020, 8, 10): "Mountain Day (moved for Tokyo 2020)",
    date(2021, 7, 22): "Marine Day (moved for Tokyo 2020)",
    date(2021, 7, 23): "Sports Day (moved for Tokyo 2020)",
    date(2021, 8, 8): "Mountain Day (moved for Tokyo 2020)",
}

# Dates the computed rules would call holidays but which were not, because the
# holiday was moved that year.
HOLIDAY_SUPPRESSED: set[date] = {
    date(2020, 7, 20),  # Marine Day moved
    date(2020, 10, 12),  # Sports Day moved
    date(2020, 8, 11),  # Mountain Day moved
    date(2021, 7, 19),  # Marine Day moved
    date(2021, 10, 11),  # Sports Day moved
    date(2021, 8, 11),  # Mountain Day moved
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _vernal_equinox(year: int) -> date:
    """Standard approximation, valid 1980-2099."""
    day = int(20.8431 + 0.242194 * (year - 1980) - (year - 1980) // 4)
    return date(year, 3, day)


def _autumnal_equinox(year: int) -> date:
    """Standard approximation, valid 1980-2099."""
    day = int(23.2488 + 0.242194 * (year - 1980) - (year - 1980) // 4)
    return date(year, 9, day)


def _base_holidays(year: int) -> dict[date, str]:
    """National holidays before substitute and citizens' holiday rules."""
    h: dict[date, str] = {
        date(year, 1, 1): "New Year's Day",
        date(year, 2, 11): "National Foundation Day",
        date(year, 4, 29): "Showa Day" if year >= 2007 else "Greenery Day",
        date(year, 5, 3): "Constitution Memorial Day",
        date(year, 5, 5): "Children's Day",
        date(year, 11, 3): "Culture Day",
        date(year, 11, 23): "Labour Thanksgiving Day",
        _vernal_equinox(year): "Vernal Equinox Day",
        _autumnal_equinox(year): "Autumnal Equinox Day",
    }

    if year >= 2007:
        h[date(year, 5, 4)] = "Greenery Day"

    # Coming of Age Day: 15 Jan until 1999, then 2nd Monday.
    h[_nth_weekday(year, 1, MONDAY, 2) if year >= 2000 else date(year, 1, 15)] = (
        "Coming of Age Day"
    )

    # Marine Day: from 1996; 20 Jul until 2002, then 3rd Monday.
    if year >= 2003:
        h[_nth_weekday(year, 7, MONDAY, 3)] = "Marine Day"
    elif year >= 1996:
        h[date(year, 7, 20)] = "Marine Day"

    # Mountain Day: from 2016.
    if year >= 2016:
        h[date(year, 8, 11)] = "Mountain Day"

    # Respect for the Aged Day: 15 Sep until 2002, then 3rd Monday.
    h[_nth_weekday(year, 9, MONDAY, 3) if year >= 2003 else date(year, 9, 15)] = (
        "Respect for the Aged Day"
    )

    # Sports Day: 10 Oct until 1999, then 2nd Monday.
    h[_nth_weekday(year, 10, MONDAY, 2) if year >= 2000 else date(year, 10, 10)] = (
        "Sports Day"
    )

    # Emperor's Birthday: 23 Dec (Heisei) -> none in 2019 -> 23 Feb (Reiwa).
    if year >= 2020:
        h[date(year, 2, 23)] = "Emperor's Birthday"
    elif year <= 2018:
        h[date(year, 12, 23)] = "Emperor's Birthday"

    return h


@lru_cache(maxsize=256)
def holidays(year: int) -> dict[date, str]:
    """All national holidays in a year, including substitute and citizens'
    holidays, with overrides applied."""
    h = _base_holidays(year)

    for d in HOLIDAY_SUPPRESSED:
        if d.year == year:
            h.pop(d, None)

    for d, reason in HOLIDAY_OVERRIDES.items():
        if d.year == year:
            h[d] = reason

    # Substitute holiday (振替休日): a holiday falling on Sunday pushes to the
    # next day that is not itself a holiday.
    for d in sorted(h):
        if d.weekday() == SUNDAY:
            nxt = d + timedelta(days=1)
            while nxt in h:
                nxt += timedelta(days=1)
            h[nxt] = "Substitute holiday"

    # Citizens' holiday (国民の休日): a single non-holiday weekday sandwiched
    # between two holidays becomes a holiday. Applies to e.g. the Silver Week
    # gap between Respect for the Aged Day and the Autumnal Equinox.
    for d in sorted(h):
        gap = d + timedelta(days=1)
        after = d + timedelta(days=2)
        if gap not in h and after in h and gap.weekday() not in (SUNDAY,):
            h[gap] = "Citizens' holiday"

    return dict(sorted(h.items()))


def is_holiday(d: date) -> bool:
    return d in holidays(d.year)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_exchange_closed(d: date) -> bool:
    """True if TSE/OSE are closed.

    Beyond weekends and national holidays, the exchanges close 1-3 January and
    31 December.
    """
    if is_weekend(d) or is_holiday(d):
        return True
    if d.month == 1 and d.day in (2, 3):
        return True
    if d.month == 12 and d.day == 31:
        return True
    return False


def is_business_day(d: date) -> bool:
    return not is_exchange_closed(d)


def next_business_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while not is_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def previous_business_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while not is_business_day(prev):
        prev -= timedelta(days=1)
    return prev


def add_business_days(d: date, n: int) -> date:
    """Advance (or retreat) n business days from d.

    n == 0 returns d unchanged even if d is not a business day; callers that
    need d itself normalised should say so explicitly.
    """
    if n == 0:
        return d
    step = next_business_day if n > 0 else previous_business_day
    cur = d
    for _ in range(abs(n)):
        cur = step(cur)
    return cur


def business_days_between(start: date, end: date) -> int:
    """Count of business days strictly after start and up to and including end."""
    if end < start:
        return -business_days_between(end, start)
    count = 0
    cur = start
    while cur < end:
        cur = next_business_day(cur)
        if cur <= end:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

# OSE derivatives session boundaries. These have moved over time (the night
# session close has been extended more than once); they are parameters rather
# than constants so a caller can supply the boundaries in force for the period
# being reconciled.
DEFAULT_NIGHT_SESSION_START = time(17, 0)
DEFAULT_NIGHT_SESSION_END = time(6, 0)
DEFAULT_DAY_SESSION_START = time(8, 45)
DEFAULT_DAY_SESSION_END = time(15, 15)


@dataclass(frozen=True, slots=True)
class SessionBoundaries:
    day_start: time = DEFAULT_DAY_SESSION_START
    day_end: time = DEFAULT_DAY_SESSION_END
    night_start: time = DEFAULT_NIGHT_SESSION_START
    night_end: time = DEFAULT_NIGHT_SESSION_END


DEFAULT_BOUNDARIES = SessionBoundaries()


def classify_session(
    ts: datetime, boundaries: SessionBoundaries = DEFAULT_BOUNDARIES
) -> Session:
    """Which session a timestamp falls in.

    `ts` is naive local (JST) time. Times at or after `night_start`, or before
    `night_end`, are the night session.
    """
    t = ts.time()
    if t >= boundaries.night_start or t < boundaries.night_end:
        return Session.NIGHT
    return Session.DAY


def trading_day(
    ts: datetime, boundaries: SessionBoundaries = DEFAULT_BOUNDARIES
) -> date:
    """The trading day (and therefore the trade date) a timestamp belongs to.

    This is the rule that gets missed. A night session trade executed on the
    evening of day D belongs to the *next* business day's trading day. A trade
    in the small hours of day D belongs to day D itself if D is a business day,
    because that session opened the previous evening.
    """
    session = classify_session(ts, boundaries)
    d = ts.date()

    if session is Session.DAY:
        if not is_business_day(d):
            raise ValueError(
                f"{ts.isoformat()} is in the day session but {d.isoformat()} "
                "is not a business day"
            )
        return d

    if ts.time() >= boundaries.night_start:
        # Evening: belongs to the next business day.
        return next_business_day(d)

    # Small hours: this session opened the previous evening, so the trading day
    # is today when today is a business day, else the next one.
    return d if is_business_day(d) else next_business_day(d)
