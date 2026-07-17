import { describe, expect, test } from "vitest";
import {
  assignmentKey,
  displayDates,
  monthWeekRows,
  mergeRecommendations,
  mondayFor,
  monthDates,
  monthWeekStarts,
  weekEnd,
  weekStartForDate,
  weekLabel,
} from "../src/features/weekly-scheduling/workspace";

describe("weekly scheduling workspace helpers", () => {
  test("finds the Monday and formats a cross-year week", () => {
    expect(mondayFor(new Date(2027, 0, 1))).toBe("2026-12-28");
    expect(weekLabel("2026-12-28", "2027-01-03")).toBe("2026/12/28 - 2027/01/03");
  });

  test("uses performance and role as the stable cell key", () => {
    expect(assignmentKey(12, 7)).toBe("12:7");
  });

  test("recommendations never replace a manual assignment", () => {
    const manual = [{ performance_id: 1, role_id: 2, actor_id: 9, source: "manual" as const }];
    const recommended = [
      { performance_id: 1, role_id: 2, actor_id: 8, source: "recommended" as const },
      { performance_id: 1, role_id: 3, actor_id: 7, source: "recommended" as const },
    ];
    expect(mergeRecommendations(manual, recommended)).toEqual([
      manual[0],
      recommended[1],
    ]);
  });

  test("builds month dates and intersecting natural weeks", () => {
    expect(monthDates(2028, 2)).toHaveLength(29);
    expect(monthDates(2026, 8)[0]).toBe("2026-08-01");
    expect(monthDates(2026, 8)[30]).toBe("2026-08-31");
    expect(monthWeekStarts(2026, 8)).toEqual([
      "2026-07-27",
      "2026-08-03",
      "2026-08-10",
      "2026-08-17",
      "2026-08-24",
      "2026-08-31",
    ]);
    expect(weekStartForDate("2026-08-09")).toBe("2026-08-03");
    expect(weekEnd("2026-08-03")).toBe("2026-08-09");
  });

  test("expands only the selected boundary week outside the month", () => {
    expect(displayDates(2026, 8, "2026-07-27").slice(0, 7)).toEqual([
      { date: "2026-07-27", adjacent: true },
      { date: "2026-07-28", adjacent: true },
      { date: "2026-07-29", adjacent: true },
      { date: "2026-07-30", adjacent: true },
      { date: "2026-07-31", adjacent: true },
      { date: "2026-08-01", adjacent: false },
      { date: "2026-08-02", adjacent: false },
    ]);
    expect(displayDates(2026, 8, "2026-08-03")).toHaveLength(31);
    expect(displayDates(2026, 8, "2026-08-31").slice(-6)).toEqual([
      { date: "2026-09-01", adjacent: true },
      { date: "2026-09-02", adjacent: true },
      { date: "2026-09-03", adjacent: true },
      { date: "2026-09-04", adjacent: true },
      { date: "2026-09-05", adjacent: true },
      { date: "2026-09-06", adjacent: true },
    ]);
  });

  test("builds complete seven-day rows for a vertical month", () => {
    const rows = monthWeekRows(2026, 8);
    expect(rows).toHaveLength(6);
    expect(rows.every((row) => row.dates.length === 7)).toBe(true);
    expect(rows.flatMap((row) => row.dates)).toHaveLength(42);
    expect(rows[0]).toEqual({
      weekStart: "2026-07-27",
      dates: [
        { date: "2026-07-27", adjacent: true },
        { date: "2026-07-28", adjacent: true },
        { date: "2026-07-29", adjacent: true },
        { date: "2026-07-30", adjacent: true },
        { date: "2026-07-31", adjacent: true },
        { date: "2026-08-01", adjacent: false },
        { date: "2026-08-02", adjacent: false },
      ],
    });
    expect(rows[5].dates[6]).toEqual({ date: "2026-09-06", adjacent: true });
  });
});
