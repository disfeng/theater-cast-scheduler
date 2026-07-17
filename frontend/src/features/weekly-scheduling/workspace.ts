import type { ScheduleAssignment } from "../../api/admin";

export function assignmentKey(performanceId: number, roleId: number) {
  return `${performanceId}:${roleId}`;
}

export function isoDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function mondayFor(value: Date) {
  const result = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const offset = (result.getDay() + 6) % 7;
  result.setDate(result.getDate() - offset);
  return isoDate(result);
}

export function shiftWeek(weekStart: string, offset: number) {
  const [year, month, day] = weekStart.split("-").map(Number);
  const value = new Date(year, month - 1, day + offset * 7);
  return mondayFor(value);
}

function localDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function shiftDate(value: string, days: number) {
  const result = localDate(value);
  result.setDate(result.getDate() + days);
  return isoDate(result);
}

export function weekStartForDate(value: string) {
  return mondayFor(localDate(value));
}

export function weekEnd(weekStart: string) {
  return shiftDate(weekStart, 6);
}

export function monthDates(year: number, month: number) {
  const total = new Date(year, month, 0).getDate();
  return Array.from({ length: total }, (_, index) => isoDate(new Date(year, month - 1, index + 1)));
}

export function monthWeekStarts(year: number, month: number) {
  return [...new Set(monthDates(year, month).map(weekStartForDate))];
}

export function monthWeekRows(year: number, month: number) {
  const monthSet = new Set(monthDates(year, month));
  return monthWeekStarts(year, month).map((weekStart) => ({
    weekStart,
    dates: Array.from({ length: 7 }, (_, index) => {
      const date = shiftDate(weekStart, index);
      return { date, adjacent: !monthSet.has(date) };
    }),
  }));
}

export function displayDates(year: number, month: number, activeWeekStart: string) {
  const base = monthDates(year, month);
  const monthSet = new Set(base);
  const activeWeek = Array.from({ length: 7 }, (_, index) => shiftDate(activeWeekStart, index));
  const intersectsMonth = activeWeek.some((value) => monthSet.has(value));
  const dates = intersectsMonth ? [...new Set([...base, ...activeWeek])].sort() : base;
  return dates.map((date) => ({ date, adjacent: !monthSet.has(date) }));
}

export function weekLabel(start: string, end: string) {
  return `${start.replace(/-/g, "/")} - ${end.replace(/-/g, "/")}`;
}

export function mergeRecommendations(current: ScheduleAssignment[], incoming: ScheduleAssignment[]) {
  const manual = new Map(current.filter((row) => row.source === "manual").map((row) => [assignmentKey(row.performance_id, row.role_id), row]));
  const result = new Map(incoming.map((row) => [assignmentKey(row.performance_id, row.role_id), row]));
  for (const [key, row] of manual) result.set(key, row);
  return [...result.values()];
}
