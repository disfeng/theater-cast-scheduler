import type { ScheduleAssignment, ScheduleWeekContext, WeeklyScheduleWorkspace } from "../../api/admin";

export type WeekScheduleState = {
  workspace: WeeklyScheduleWorkspace;
  originalAssignments: ScheduleAssignment[];
  assignments: ScheduleAssignment[];
  dirty: boolean;
  loading: boolean;
  error: string;
};

export type MonthScheduleState = Record<string, WeekScheduleState>;

function normalized(assignments: ScheduleAssignment[]) {
  return assignments
    .map(({ performance_id, role_id, actor_id, source }) => ({ performance_id, role_id, actor_id, source }))
    .sort((left, right) => left.performance_id - right.performance_id || left.role_id - right.role_id || left.actor_id - right.actor_id || left.source.localeCompare(right.source));
}

function sameAssignments(left: ScheduleAssignment[], right: ScheduleAssignment[]) {
  return JSON.stringify(normalized(left)) === JSON.stringify(normalized(right));
}

export function createMonthState(workspaces: WeeklyScheduleWorkspace[]): MonthScheduleState {
  return Object.fromEntries(workspaces.map((workspace) => [workspace.week_start, {
    workspace,
    originalAssignments: [...workspace.assignments],
    assignments: [...workspace.assignments],
    dirty: false,
    loading: false,
    error: "",
  }]));
}

export function replaceWeekAssignments(state: MonthScheduleState, weekStart: string, assignments: ScheduleAssignment[]): MonthScheduleState {
  const current = state[weekStart];
  if (!current) return state;
  return {
    ...state,
    [weekStart]: {
      ...current,
      assignments: [...assignments],
      dirty: !sameAssignments(current.originalAssignments, assignments),
    },
  };
}

export function dirtyWeekStarts(state: MonthScheduleState) {
  return Object.keys(state).filter((weekStart) => state[weekStart].dirty).sort();
}

export function combinedAssignments(state: MonthScheduleState) {
  return Object.keys(state).sort().flatMap((weekStart) => state[weekStart].assignments);
}

export function contextWeeks(state: MonthScheduleState): ScheduleWeekContext[] {
  return Object.keys(state).sort().map((weekStart) => ({
    week_start: weekStart,
    assignments: state[weekStart].assignments,
  }));
}

export function performanceWeekMap(state: MonthScheduleState) {
  return new Map(Object.entries(state).flatMap(([weekStart, week]) => (
    week.workspace.performances.map((performance) => [performance.id, weekStart] as const)
  )));
}

export function aggregateScheduleCounts(state: MonthScheduleState) {
  return Object.values(state).reduce((counts, week) => ({
    assigned: counts.assigned + week.assignments.length,
    total: counts.total + week.workspace.performances.length * week.workspace.roles.length,
    conflicts: counts.conflicts + week.workspace.conflicts.length,
    warnings: counts.warnings + week.workspace.warnings.length,
  }), { assigned: 0, total: 0, conflicts: 0, warnings: 0 });
}
