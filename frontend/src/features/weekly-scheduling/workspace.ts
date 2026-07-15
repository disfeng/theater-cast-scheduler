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

export function weekLabel(start: string, end: string) {
  return `${start.replace(/-/g, "/")} - ${end.replace(/-/g, "/")}`;
}

export function mergeRecommendations(current: ScheduleAssignment[], incoming: ScheduleAssignment[]) {
  const manual = new Map(current.filter((row) => row.source === "manual").map((row) => [assignmentKey(row.performance_id, row.role_id), row]));
  const result = new Map(incoming.map((row) => [assignmentKey(row.performance_id, row.role_id), row]));
  for (const [key, row] of manual) result.set(key, row);
  return [...result.values()];
}
