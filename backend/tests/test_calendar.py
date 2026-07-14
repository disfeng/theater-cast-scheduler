from datetime import date, time

from app.services.calendar import generate_month_performances


def test_generate_month_uses_weekly_template_and_closed_dates():
    template = {
        "monday": [(1, "午场", time(14)), (2, "晚场", time(19, 30))],
        "tuesday": [(2, "晚场", time(19, 30))],
        "wednesday": [(2, "晚场", time(19, 30))],
        "thursday": [(2, "晚场", time(19, 30))],
        "friday": [(1, "午场", time(14)), (2, "晚场", time(19, 30))],
        "saturday": [(1, "午场", time(14)), (2, "晚场", time(19, 30))],
        "sunday": [(1, "午场", time(14)), (2, "晚场", time(19, 30))],
    }

    drafts = generate_month_performances(
        year=2026,
        month=6,
        weekly_template=template,
        closed_dates={date(2026, 6, 2)},
    )

    june_1 = [draft.slot_name for draft in drafts if draft.date == date(2026, 6, 1)]
    june_2 = [draft.slot_name for draft in drafts if draft.date == date(2026, 6, 2)]
    june_3 = [draft.slot_name for draft in drafts if draft.date == date(2026, 6, 3)]

    assert june_1 == ["午场", "晚场"]
    assert june_2 == []
    assert june_3 == ["晚场"]
