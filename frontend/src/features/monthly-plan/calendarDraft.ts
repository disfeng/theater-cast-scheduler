import type { Performance, WeeklyTemplate } from "../../api/admin";

export type MonthlyCalendarDraft = Record<string, number[]>;

const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

export function nextMonth(reference: Date) {
  const value = new Date(reference.getFullYear(), reference.getMonth() + 1, 1);
  return { year: value.getFullYear(), month: value.getMonth() + 1 };
}

export function formatDate(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function buildCalendarDraft({
  year,
  month,
  template,
  performances,
}: {
  year: number;
  month: number;
  template: WeeklyTemplate;
  performances: Performance[];
}): MonthlyCalendarDraft {
  const draft: MonthlyCalendarDraft = {};
  const days = new Date(year, month, 0).getDate();
  for (let day = 1; day <= days; day += 1) {
    const key = formatDate(year, month, day);
    draft[key] = performances.length
      ? []
      : [...(template[WEEKDAYS[new Date(year, month - 1, day).getDay()]] || [])];
  }
  for (const performance of performances) {
    if (performance.performance_date in draft) {
      draft[performance.performance_date].push(performance.theater_slot_id);
    }
  }
  return draft;
}

export function toggleDraftSlot(
  draft: MonthlyCalendarDraft,
  performanceDate: string,
  slotId: number,
): MonthlyCalendarDraft {
  const current = draft[performanceDate] || [];
  return {
    ...draft,
    [performanceDate]: current.includes(slotId)
      ? current.filter((id) => id !== slotId)
      : [...current, slotId],
  };
}

export function serializeDraft(draft: MonthlyCalendarDraft) {
  return Object.entries(draft)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([performance_date, theater_slot_ids]) => ({
      performance_date,
      theater_slot_ids,
    }));
}
