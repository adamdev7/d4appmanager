"""Gifting calendar for a Canadian / Quebec jewelry store, with a production lookahead.

Creative for a peak should be ready 4 to 8 weeks before it, so each occasion is tagged:
- ``in_market``: peak within 27 days -> last-minute / countdown angles
- ``prep_now``: 28 to 56 days out -> produce now so ads are learning before the peak
- ``upcoming``: 57 to 84 days out -> plan, test angles cheaply
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

LOOKAHEAD_DAYS = 84


@dataclass(frozen=True)
class Occasion:
    key: str
    name_en: str
    name_fr: str
    angle: str


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th weekday (Mon=0) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _occasion_dates(year: int) -> list[tuple[Occasion, date, date | None]]:
    thanksgiving_us = _nth_weekday(year, 11, 3, 4)
    black_friday = thanksgiving_us + timedelta(days=1)
    return [
        (Occasion("valentines", "Valentine's Day", "Saint-Valentin", "romance, 'for her', couples"), date(year, 2, 14), None),
        (Occasion("womens_day", "International Women's Day", "Journée internationale des femmes", "self-gifting, empowerment"), date(year, 3, 8), None),
        (Occasion("mothers_day", "Mother's Day", "Fête des Mères", "gift for mom, family, gratitude"), _nth_weekday(year, 5, 6, 2), None),
        (Occasion("wedding_season", "Wedding season", "Saison des mariages", "bridal, bridesmaids, guest looks"), date(year, 5, 15), date(year, 9, 30)),
        (Occasion("graduation", "Graduation / prom", "Graduation / bal des finissants", "milestone gift, prom looks"), date(year, 6, 1), date(year, 6, 30)),
        (Occasion("fathers_day", "Father's Day", "Fête des Pères", "only if men's pieces exist; else skip"), _nth_weekday(year, 6, 6, 3), None),
        (Occasion("black_friday", "Black Friday", "Vendredi fou", "gift planning; only real offers"), black_friday, None),
        (Occasion("cyber_monday", "Cyber Monday", "Cyberlundi", "online gifting; only real offers"), black_friday + timedelta(days=3), None),
        (Occasion("christmas", "Christmas", "Noël", "gift for her, stocking, last-minute gift"), date(year, 12, 25), None),
        (Occasion("boxing_day", "Boxing Day", "Boxing Day / Lendemain de Noël", "self-gift after the holidays; only real offers"), date(year, 12, 26), None),
    ]


EVERGREEN = [
    {"key": "birthday", "name_en": "Birthdays", "name_fr": "Anniversaires", "angle": "birthday gift, month-of-birth moments"},
    {"key": "anniversary", "name_en": "Anniversaries", "name_fr": "Anniversaires de couple", "angle": "couples, milestones"},
    {"key": "push_present", "name_en": "Push present", "name_fr": "Cadeau de naissance", "angle": "new moms, gratitude"},
    {"key": "self_gift", "name_en": "Treat yourself", "name_fr": "Se gâter", "angle": "self-love, everyday luxury"},
]


def _window(days_until: int) -> str:
    if days_until <= 27:
        return "in_market"
    if days_until <= 56:
        return "prep_now"
    return "upcoming"


def upcoming_occasions(today: date, lookahead_days: int = LOOKAHEAD_DAYS) -> list[dict]:
    """Occasions whose peak (or active season) falls within the lookahead, soonest first."""
    out: list[dict] = []
    for year in (today.year, today.year + 1):
        for occ, start, end in _occasion_dates(year):
            last_day = end or start
            if last_day < today:
                continue
            days_until = max(0, (start - today).days)
            if days_until > lookahead_days:
                continue
            out.append(
                {
                    "key": occ.key,
                    "name": occ.name_en,
                    "name_fr": occ.name_fr,
                    "date": start.isoformat(),
                    "ends": end.isoformat() if end else None,
                    "days_until": days_until,
                    "weeks_until": round(days_until / 7, 1),
                    "window": "in_market" if start <= today <= last_day else _window(days_until),
                    "angle": occ.angle,
                }
            )
    out.sort(key=lambda o: o["days_until"])
    return out
