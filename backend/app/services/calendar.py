from dataclasses import dataclass
from datetime import date, time
from calendar import monthrange


WEEKDAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


@dataclass(frozen=True)
class PerformanceDraft:
    date: date
    theater_slot_id: int
    slot_name: str
    start_time: time


def generate_month_performances(
    year: int,
    month: int,
    weekly_template: dict[str, list[tuple[int, str, time]]],
    closed_dates: set[date],
) -> list[PerformanceDraft]:
    _, days_in_month = monthrange(year, month)
    drafts: list[PerformanceDraft] = []

    for day in range(1, days_in_month + 1):
        current = date(year, month, day)
        if current in closed_dates:
            continue
        weekday = WEEKDAY_NAMES[current.weekday()]
        for slot_id, slot_name, start_time in weekly_template.get(weekday, []):
            drafts.append(PerformanceDraft(current, slot_id, slot_name, start_time))

    return drafts
