from datetime import date

from app.services.calendar import generate_month_performances


def test_generate_month_uses_weekly_template_and_closed_dates():
    template = {
        "monday": ["early", "late"],
        "tuesday": ["late"],
        "wednesday": ["late"],
        "thursday": ["late"],
        "friday": ["early", "late"],
        "saturday": ["early", "late"],
        "sunday": ["early", "late"],
    }

    drafts = generate_month_performances(
        year=2026,
        month=6,
        weekly_template=template,
        closed_dates={date(2026, 6, 2)},
    )

    june_1 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 1)]
    june_2 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 2)]
    june_3 = [draft.slot for draft in drafts if draft.date == date(2026, 6, 3)]

    assert june_1 == ["early", "late"]
    assert june_2 == []
    assert june_3 == ["late"]
