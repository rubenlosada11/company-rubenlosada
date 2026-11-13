"""Semanas ISO en UTC y ventana de cálculo (`app/reporting/weeks.py`, PIPELINE_DESIGN.md §6.2 y §7).

Ejecutar desde services/api: uv run pytest tests/reporting/test_weeks.py
"""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.reporting.weeks import (
    MAX_WEEKS,
    WeekWindow,
    WindowError,
    last_complete_week,
    resolve_window,
    week_bounds,
    week_start_of,
)
from tests.reporting.helpers import CURRENT, NOW, W1, W2


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 11, 2, 0, 0, 0, tzinfo=UTC), date(2026, 11, 2)),  # lunes 00:00 → esa semana
        (datetime(2026, 11, 8, 23, 59, 59, tzinfo=UTC), date(2026, 11, 2)),  # domingo 23:59:59 → la misma
        (datetime(2026, 11, 9, 0, 0, 0, tzinfo=UTC), date(2026, 11, 9)),  # lunes siguiente → la siguiente
        (datetime(2026, 11, 5, 12, 0), date(2026, 11, 2)),  # sin zona horaria = UTC
        (date(2026, 11, 8), date(2026, 11, 2)),
        (datetime(2027, 1, 1, tzinfo=UTC), date(2026, 12, 28)),  # semana ISO que cruza el año
    ],
)
def test_week_start_is_the_utc_monday(moment, expected):
    assert week_start_of(moment) == expected


def test_week_start_converts_other_time_zones_to_utc():
    # Lunes 00:30 en Zaragoza (UTC+1) es domingo 23:30 UTC: semana anterior.
    zaragoza = timezone(timedelta(hours=1))
    assert week_start_of(datetime(2026, 11, 9, 0, 30, tzinfo=zaragoza)) == date(2026, 11, 2)
    # Domingo 20:00 en Los Ángeles (UTC−8) es lunes 04:00 UTC: semana siguiente.
    los_angeles = timezone(timedelta(hours=-8))
    assert week_start_of(datetime(2026, 11, 8, 20, 0, tzinfo=los_angeles)) == date(2026, 11, 9)


def test_week_bounds_are_monday_to_monday_end_exclusive():
    start, end = week_bounds(W2)
    assert start == datetime(2026, 11, 2, tzinfo=UTC)
    assert end == datetime(2026, 11, 9, tzinfo=UTC)


def test_last_complete_week_never_is_the_current_one():
    assert last_complete_week(NOW) == W2
    assert last_complete_week(datetime(2026, 11, 9, 0, 0, tzinfo=UTC)) == W2  # el lunes a las 00:00 ya terminó W2


def test_default_window_is_the_last_two_complete_weeks():
    window = resolve_window(None, now=NOW)
    assert window == WeekWindow(first=W1, last=W2)
    assert window.weeks == [W1, W2]
    assert window.start == datetime(2026, 10, 26, tzinfo=UTC)
    assert window.end == datetime(2026, 11, 9, tzinfo=UTC)


def test_window_ends_at_the_requested_week():
    window = resolve_window(W1, weeks=3, now=NOW)
    assert window.weeks == [date(2026, 10, 12), date(2026, 10, 19), W1]
    assert resolve_window(W2, weeks=1, now=NOW).weeks == [W2]


@pytest.mark.parametrize(
    ("week_start", "weeks", "field"),
    [
        (date(2026, 11, 3), 1, "week_start"),  # martes
        (CURRENT, 1, "week_start"),  # semana en curso
        (CURRENT + timedelta(days=7), 1, "week_start"),  # futura
        (None, 0, "weeks"),
        (None, MAX_WEEKS + 1, "weeks"),
    ],
)
def test_invalid_windows_name_the_parameter(week_start, weeks, field):
    with pytest.raises(WindowError) as error:
        resolve_window(week_start, weeks, now=NOW)
    assert error.value.field == field
