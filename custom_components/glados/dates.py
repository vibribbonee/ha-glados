"""Dates people say, worked out in Python so the model never has to.

Small models get weekdays and "in N days" wrong, so every tool takes the words
people use (today, tomorrow, a weekday, a date) and returns the date spelled
out, ready to be read aloud.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re

from homeassistant.util import dt as dt_util

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^(\d{1,2})[:.h]?(\d{2})?")


def parse_time(value: str | time | None) -> time | None:
    """A time of day from 15:00, 15.00, 1500, 9 or a time object."""
    if isinstance(value, time):
        return value
    match = _TIME.match((value or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def resolve_date(day: str | None, now: datetime | None = None) -> date:
    """The date meant by today, tomorrow, a weekday or YYYY-MM-DD.

    A weekday is the next one coming, today included; anything unknown is today.
    """
    now = now or dt_util.now()
    d = (day or "").strip().lower()
    if d == "tomorrow":
        return now.date() + timedelta(days=1)
    if d in WEEKDAYS:
        return now.date() + timedelta(days=(WEEKDAYS.index(d) - now.weekday()) % 7)
    if _ISO_DATE.match(d):
        return date.fromisoformat(d)
    return now.date()


def resolve_moment(day: str | None, at: time, now: datetime | None = None) -> datetime:
    """The next moment matching a day and a time of day, in local time.

    No day: today if that time is still to come, otherwise tomorrow. A weekday
    that is today but already past means next week.
    """
    now = now or dt_util.now()
    d = (day or "").strip().lower()
    moment = datetime.combine(resolve_date(d, now), at, tzinfo=now.tzinfo)
    if moment < now:
        if d in WEEKDAYS:
            moment += timedelta(days=7)
        elif d not in ("today", "tomorrow") and not _ISO_DATE.match(d):
            moment += timedelta(days=1)
    return moment


def spoken_date(value: date | datetime) -> str:
    """Friday 27 November."""
    return f"{value.strftime('%A')} {value.day} {value.strftime('%B')}"


def days_away(value: date | datetime, now: datetime | None = None) -> str:
    """today, tomorrow, or in N days."""
    now = now or dt_util.now()
    target = value.date() if isinstance(value, datetime) else value
    diff = (target - now.date()).days
    if diff <= 0:
        return "today"
    if diff == 1:
        return "tomorrow"
    return f"in {diff} days"
