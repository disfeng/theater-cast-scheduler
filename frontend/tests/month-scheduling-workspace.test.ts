import { describe, expect, test } from "vitest";
import type { WeeklyScheduleWorkspace } from "../src/api/admin";
import {
  aggregateScheduleCounts,
  combinedAssignments,
  contextWeeks,
  createMonthState,
  dirtyWeekStarts,
  performanceWeekMap,
  replaceWeekAssignments,
} from "../src/features/weekly-scheduling/month-workspace";

function workspace(weekStart: string, performanceId: number, actorId?: number): WeeklyScheduleWorkspace {
  return {
    theater_id: 1,
    week_start: weekStart,
    week_end: "2026-08-09",
    batch_id: null,
    status: "uncreated",
    version: 0,
    updated_at: null,
    published_at: null,
    performances: [{ id: performanceId, performance_date: "2026-08-03", slot_name: "早场", start_time: "12:30:00", sort_order: 0 }],
    roles: [{ id: 20, name: "柳知雨", group_name: "女" }],
    actors: [],
    assignments: actorId ? [{ performance_id: performanceId, role_id: 20, actor_id: actorId, source: "manual" }] : [],
    conflicts: [],
    conflict_summary: {},
    warnings: [],
    warning_summary: {},
    empty_slots: actorId ? [] : [{ performance_id: performanceId, role_id: 20 }],
    unsatisfied_designations: [],
    unsatisfied_wishes: [],
  };
}

describe("month scheduling workspace state", () => {
  test("keeps weeks isolated and tracks dirty assignments by content", () => {
    const initial = createMonthState([
      workspace("2026-07-27", 10),
      workspace("2026-08-03", 11),
    ]);
    const edited = replaceWeekAssignments(initial, "2026-08-03", [
      { performance_id: 11, role_id: 20, actor_id: 30, source: "manual" },
    ]);

    expect(dirtyWeekStarts(edited)).toEqual(["2026-08-03"]);
    expect(edited["2026-07-27"].assignments).toEqual([]);
    expect(edited["2026-08-03"].dirty).toBe(true);

    const restored = replaceWeekAssignments(edited, "2026-08-03", []);
    expect(dirtyWeekStarts(restored)).toEqual([]);
  });

  test("serializes every local week and aggregates without crossing keys", () => {
    let state = createMonthState([
      workspace("2026-07-27", 10, 30),
      workspace("2026-08-03", 11),
    ]);
    state = replaceWeekAssignments(state, "2026-08-03", [
      { performance_id: 11, role_id: 20, actor_id: 31, source: "manual" },
    ]);
    state["2026-07-27"].workspace.conflicts = [{ code: "actor_on_leave", message: "请假", performance_id: 10, role_id: 20, actor_id: 30 }];
    state["2026-08-03"].workspace.warnings = [{ code: "consecutive_limit_reached", message: "达到上限", performance_id: 11, role_id: 20, actor_id: 31 }];

    expect(combinedAssignments(state)).toHaveLength(2);
    expect(contextWeeks(state)).toEqual([
      { week_start: "2026-07-27", assignments: state["2026-07-27"].assignments },
      { week_start: "2026-08-03", assignments: state["2026-08-03"].assignments },
    ]);
    expect(performanceWeekMap(state)).toEqual(new Map([[10, "2026-07-27"], [11, "2026-08-03"]]));
    expect(aggregateScheduleCounts(state)).toEqual({ assigned: 2, total: 2, conflicts: 1, warnings: 1 });
  });
});
