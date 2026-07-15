import { describe, expect, test } from "vitest";
import {
  assignmentKey,
  mergeRecommendations,
  mondayFor,
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
});
