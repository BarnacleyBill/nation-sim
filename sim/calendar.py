"""Turning a day counter into years, seasons and weeks."""
from .config import DAYS_PER_YEAR, DAYS_PER_SEASON, DAYS_PER_WEEK, SEASONS


def year(day):
    return day // DAYS_PER_YEAR + 1


def season(day):
    return SEASONS[(day % DAYS_PER_YEAR) // DAYS_PER_SEASON]


def week_of_year(day):
    return (day % DAYS_PER_YEAR) // DAYS_PER_WEEK + 1


def is_week_start(day):
    return day % DAYS_PER_WEEK == 0


def is_week_end(day):
    return day % DAYS_PER_WEEK == DAYS_PER_WEEK - 1


def days_until_spring(day):
    d = day % DAYS_PER_YEAR
    return (DAYS_PER_YEAR - d) % DAYS_PER_YEAR


def age_years(birth_day, today):
    return (today - birth_day) / DAYS_PER_YEAR


def label(day):
    return f"Year {year(day)}, {season(day)}, week {week_of_year(day)}"
