"""Semanas ISO en UTC y ventana de cálculo del pipeline (PIPELINE_DESIGN.md §6.2 y §7).

- `week_start` es el **lunes** de la semana ISO; la semana es `[lunes 00:00 UTC, lunes siguiente 00:00 UTC)`.
- Solo se calculan semanas **completas**: la más reciente posible es la anterior a la semana en curso.
- La ventana por defecto son las `DEFAULT_WEEKS` últimas semanas completas: recalcular también la anterior recoge
  eventos tardíos y rellena la semana de una ejecución fallida (autorreparación).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

WEEK = timedelta(days=7)
DEFAULT_WEEKS = 2
MAX_WEEKS = 53


class WindowError(ValueError):
    """Parámetros de ventana no válidos. `field` es el parámetro al que se atribuye el error."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def week_start_of(moment: datetime | date) -> date:
    """Lunes (UTC) de la semana ISO que contiene `moment`. Una fecha y hora sin zona se interpreta como UTC."""
    if isinstance(moment, datetime):
        moment = (moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)).date()
    return moment - timedelta(days=moment.weekday())


def is_monday(day: date) -> bool:
    return day.weekday() == 0


def last_complete_week(now: datetime | None = None) -> date:
    """`week_start` de la última semana terminada respecto a `now` (UTC)."""
    return week_start_of(now or datetime.now(UTC)) - WEEK


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    """`[inicio, fin)` de la semana en UTC."""
    start = datetime.combine(week_start, time.min, tzinfo=UTC)
    return start, start + WEEK


@dataclass(frozen=True)
class WeekWindow:
    """Semanas consecutivas de `first` a `last` (ambos lunes, inclusive)."""

    first: date
    last: date

    @property
    def weeks(self) -> list[date]:
        count = (self.last - self.first).days // 7 + 1
        return [self.first + WEEK * index for index in range(count)]

    @property
    def start(self) -> datetime:
        """Inicio de la ventana (UTC, inclusivo)."""
        return week_bounds(self.first)[0]

    @property
    def end(self) -> datetime:
        """Fin de la ventana (UTC, exclusivo)."""
        return week_bounds(self.last)[1]


def resolve_window(week_start: date | None, weeks: int = DEFAULT_WEEKS, now: datetime | None = None) -> WeekWindow:
    """Ventana de `weeks` semanas que termina en `week_start` (por defecto, la última semana completa).

    `WindowError` si `week_start` no es un lunes, si su semana aún no ha terminado o si `weeks` no está en
    `[1, MAX_WEEKS]`.
    """
    if not 1 <= weeks <= MAX_WEEKS:
        raise WindowError("weeks", f"weeks debe estar entre 1 y {MAX_WEEKS}.")
    latest = last_complete_week(now)
    if week_start is None:
        week_start = latest
    elif not is_monday(week_start):
        raise WindowError("week_start", "week_start debe ser un lunes (inicio de la semana ISO).")
    elif week_start > latest:
        raise WindowError(
            "week_start",
            f"La semana de {week_start.isoformat()} aún no ha terminado: la última completa es {latest.isoformat()}.",
        )
    return WeekWindow(first=week_start - WEEK * (weeks - 1), last=week_start)
