import type { PerformanceWish, Predesignation } from "../../api/admin";

export type WorkspaceTotals = {
  players: number;
  designations: number;
  wishes: number;
  pending: number;
  conflicts: number;
};

export type PerformanceSummary = {
  id: number;
  performance_date: string;
  slot_name: string;
  start_time: string;
  status: string;
  totals: WorkspaceTotals;
};

export type DesignationMonthWorkspace = {
  theater_id: number;
  year: number;
  month: number;
  totals: WorkspaceTotals;
  days: { date: string; performances: PerformanceSummary[] }[];
};

export type DesignationConflictProjection = {
  code: string;
  severity: "warning" | "hard";
  message: string;
  designation_id: number | null;
};

export type PerformanceWorkspace = {
  performance: PerformanceSummary & { theater_id: number; theater_name: string };
  players: {
    id: number;
    player_id: number | null;
    player_name: string;
    theater_visit_count: number | null;
    role_visit_count: number | null;
    role_id: number | null;
    role_name: string | null;
    status: string;
  }[];
  designations: Predesignation[];
  wishes: PerformanceWish[];
  conflicts: DesignationConflictProjection[];
};
