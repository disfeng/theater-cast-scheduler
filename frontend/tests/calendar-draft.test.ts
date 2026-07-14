import { describe, expect, test } from "vitest";
import { buildCalendarDraft, nextMonth, serializeDraft, toggleDraftSlot } from "../src/features/monthly-plan/calendarDraft";

const template = { monday: [1, 2], tuesday: [2] };

describe("monthly calendar draft", () => {
  test("defaults to the next month across year boundaries", () => {
    expect(nextMonth(new Date(2026, 11, 15))).toEqual({ year: 2027, month: 1 });
  });

  test("builds from the weekly template when no performances exist", () => {
    const draft = buildCalendarDraft({ year: 2026, month: 8, template, performances: [] });
    expect(draft["2026-08-03"]).toEqual([1, 2]);
    expect(draft["2026-08-04"]).toEqual([2]);
  });

  test("uses persisted performances instead of the template", () => {
    const draft = buildCalendarDraft({
      year: 2026,
      month: 8,
      template,
      performances: [{ performance_date: "2026-08-03", theater_slot_id: 2 }] as any,
    });
    expect(draft["2026-08-03"]).toEqual([2]);
    expect(draft["2026-08-04"]).toEqual([]);
  });

  test("toggles slots immutably and serializes every day", () => {
    const draft = { "2026-08-03": [1, 2], "2026-08-04": [] };
    const changed = toggleDraftSlot(draft, "2026-08-03", 1);
    expect(changed).not.toBe(draft);
    expect(changed["2026-08-03"]).toEqual([2]);
    expect(serializeDraft(changed)).toContainEqual({ performance_date: "2026-08-03", theater_slot_ids: [2] });
  });
});
