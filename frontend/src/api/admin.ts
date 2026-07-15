import { apiClient } from "./client";

export type Theater = { id: number; name: string; is_active: boolean };
export type TheaterSlot = {
  id: number;
  theater_id: number;
  name: string;
  start_time: string;
  sort_order: number;
  is_active: boolean;
};
export type WeeklyTemplate = Record<string, number[]>;
export type Role = { id: number; theater_id: number; name: string; group_name: string | null; is_active: boolean };
export type WeeklyBatch = {
  id: number;
  theater_id: number;
  week_start: string;
  status: "draft" | "ready" | "scheduled";
  created_at: string;
};

export type ImportDraftItem = {
  id: number;
  import_draft_id: number;
  item_kind: "designation" | "wish" | "unresolved";
  raw_line: string | null;
  designation_type: "universal" | "top_three" | "paired" | null;
  player_name: string | null;
  actor_name_raw: string | null;
  role_name_raw: string | null;
  actor_id: number | null;
  role_id: number | null;
  target_performance_id: number | null;
  note: string | null;
  validation_status: "valid" | "invalid";
  failure_reason: string | null;
  confirmed_at: string | null;
  designation_id: number | null;
  wish_id: number | null;
};

export type ImportDraft = {
  id: number;
  weekly_batch_id: number;
  raw_text: string;
  status: "draft" | "partially_confirmed" | "confirmed";
  created_at: string;
  updated_at: string;
  items: ImportDraftItem[];
};

export type BatchSchedulingInputs = {
  designations: {
    designation_type: "universal" | "top_three" | "paired";
    player_name: string;
    role_id: number;
    actor_id: number;
    target_performance_id: number | null;
    submitted_at: string;
    failure_reason: string | null;
  }[];
  wishes: {
    player_name: string;
    role_id: number;
    actor_id: number;
    note: string | null;
  }[];
};

export type Actor = {
  id: number;
  display_name: string;
  max_consecutive_performances: number;
  rating_level: "high" | "normal" | "low" | "suspended";
  low_rating_monthly_cap: number | null;
  notes: string | null;
  role_ids: number[];
};

export type Performance = {
  id: number;
  theater_id: number;
  performance_date: string;
  theater_slot_id: number;
  slot_name_snapshot: string;
  start_time_snapshot: string;
  status: string;
};

export type LeaveRequest = {
  id: number;
  actor_id: number;
  actor_name: string;
  leave_date: string;
  status: string;
  note: string | null;
};

export type ScheduleAssignment = {
  performance_id: number;
  role_id: number;
  actor_id: number;
  source: "manual" | "recommended";
  conflict_codes?: string[];
};
export type ScheduleConflict = {
  code: string; message: string; performance_id: number | null; role_id: number | null; actor_id: number | null;
};
export type WeeklyScheduleWorkspace = {
  theater_id: number; week_start: string; week_end: string; batch_id: number | null;
  status: "uncreated" | "draft" | "ready" | "scheduled"; version: number;
  updated_at: string | null; published_at: string | null;
  performances: { id: number; performance_date: string; slot_name: string; start_time: string; sort_order: number }[];
  roles: { id: number; name: string; group_name: string | null }[];
  actors: { id: number; display_name: string; rating_level: string; max_consecutive_performances: number; low_rating_monthly_cap: number | null; role_ids: number[]; weekly_count: number; monthly_count: number }[];
  assignments: ScheduleAssignment[]; conflicts: ScheduleConflict[]; conflict_summary: Record<string, number>;
  warnings: ScheduleConflict[]; warning_summary: Record<string, number>;
  empty_slots: { performance_id: number; role_id: number }[];
  unsatisfied_designations: Record<string, unknown>[]; unsatisfied_wishes: Record<string, unknown>[];
};
export type ScheduleMutation = {
  theater_id: number; week_start: string; expected_version: number; assignments: ScheduleAssignment[]; confirm_conflicts?: boolean;
};

export const adminApi = {
  async getTheaters(token: string, includeInactive = false): Promise<Theater[]> {
    return apiClient.request(includeInactive ? "/admin/theaters?include_inactive=true" : "/admin/theaters", { token });
  },

  async createTheater(token: string, payload: { name: string }): Promise<Theater> {
    return apiClient.request("/admin/theaters", { method: "POST", token, body: payload });
  },

  async updateTheater(token: string, theaterId: number, payload: { name: string }): Promise<Theater> {
    return apiClient.request(`/admin/theaters/${theaterId}`, { method: "PATCH", token, body: payload });
  },

  async deleteTheater(token: string, theaterId: number): Promise<void> {
    return apiClient.request(`/admin/theaters/${theaterId}`, { method: "DELETE", token });
  },

  async archiveTheater(token: string, theaterId: number): Promise<Theater> {
    return apiClient.request(`/admin/theaters/${theaterId}/archive`, { method: "POST", token });
  },

  async restoreTheater(token: string, theaterId: number): Promise<Theater> {
    return apiClient.request(`/admin/theaters/${theaterId}/restore`, { method: "POST", token });
  },

  async getTheaterSlots(token: string, theaterId: number, includeInactive = false): Promise<TheaterSlot[]> {
    return apiClient.request(`/admin/theaters/${theaterId}/slots?include_inactive=${includeInactive}`, { token });
  },

  async createTheaterSlot(token: string, theaterId: number, payload: { name: string; start_time: string; sort_order: number }): Promise<TheaterSlot> {
    return apiClient.request(`/admin/theaters/${theaterId}/slots`, { method: "POST", token, body: payload });
  },

  async updateTheaterSlot(token: string, slotId: number, payload: { name: string; start_time: string; sort_order: number }): Promise<TheaterSlot> {
    return apiClient.request(`/admin/theater-slots/${slotId}`, { method: "PATCH", token, body: payload });
  },

  async deleteTheaterSlot(token: string, slotId: number): Promise<void> {
    return apiClient.request(`/admin/theater-slots/${slotId}`, { method: "DELETE", token });
  },

  async archiveTheaterSlot(token: string, slotId: number): Promise<TheaterSlot> {
    return apiClient.request(`/admin/theater-slots/${slotId}/archive`, { method: "POST", token });
  },

  async restoreTheaterSlot(token: string, slotId: number): Promise<TheaterSlot> {
    return apiClient.request(`/admin/theater-slots/${slotId}/restore`, { method: "POST", token });
  },

  async getWeeklyTemplate(token: string, theaterId: number): Promise<WeeklyTemplate> {
    return apiClient.request(`/admin/theaters/${theaterId}/weekly-template`, { token });
  },

  async updateWeeklyTemplate(token: string, theaterId: number, template: WeeklyTemplate): Promise<WeeklyTemplate> {
    return apiClient.request(`/admin/theaters/${theaterId}/weekly-template`, { method: "PUT", token, body: { template } });
  },

  async getRoles(token: string, theaterId?: number, includeInactive = false): Promise<Role[]> {
    if (!theaterId && !includeInactive) return apiClient.request("/admin/roles", { token });
    const query = new URLSearchParams({ include_inactive: String(includeInactive) });
    if (theaterId) query.set("theater_id", String(theaterId));
    return apiClient.request(`/admin/roles?${query}`, { token });
  },

  async createRole(token: string, payload: { theater_id: number; name: string; group_name: string | null }): Promise<Role> {
    return apiClient.request("/admin/roles", { method: "POST", token, body: payload });
  },

  async updateRole(token: string, roleId: number, payload: { name: string; group_name: string | null }): Promise<Role> {
    return apiClient.request(`/admin/roles/${roleId}`, { method: "PATCH", token, body: payload });
  },

  async deleteRole(token: string, roleId: number): Promise<void> {
    return apiClient.request(`/admin/roles/${roleId}`, { method: "DELETE", token });
  },

  async getActors(token: string): Promise<Actor[]> {
    return apiClient.request("/admin/actors", { token });
  },

  async createActor(token: string, payload: Omit<Actor, "id" | "role_ids">): Promise<Actor> {
    return apiClient.request("/admin/actors", { method: "POST", token, body: payload });
  },

  async generateMonthlyPlan(token: string, payload: { theater_id: number; year: number; month: number; closed_dates: string[] }): Promise<Performance[]> {
    return apiClient.request("/admin/monthly-plan/generate", { method: "POST", token, body: payload });
  },

  async replaceMonthlyPlan(token: string, payload: { theater_id: number; year: number; month: number; days: { performance_date: string; theater_slot_ids: number[] }[] }): Promise<Performance[]> {
    return apiClient.request("/admin/monthly-plan", { method: "PUT", token, body: payload });
  },

  async getPerformances(token: string, theaterId: number, year: number, month: number): Promise<Performance[]> {
    return apiClient.request(`/admin/performances?theater_id=${theaterId}&year=${year}&month=${month}`, { token });
  },

  async createPerformance(token: string, payload: { theater_id: number; performance_date: string; theater_slot_id: number }): Promise<Performance> {
    return apiClient.request("/admin/performances", { method: "POST", token, body: payload });
  },

  async deletePerformance(token: string, performanceId: number): Promise<{ status: string }> {
    return apiClient.request(`/admin/performances/${performanceId}`, { method: "DELETE", token });
  },

  async getLeaveRequests(token: string): Promise<LeaveRequest[]> {
    return apiClient.request("/admin/leave-requests", { token });
  },

  async reviewLeaveRequest(token: string, leaveId: number, status: "approved" | "rejected" | "locked"): Promise<LeaveRequest> {
    return apiClient.request(`/admin/leave-requests/${leaveId}/review`, { method: "POST", token, body: { status } });
  },

  async getWeeklyBatches(token: string): Promise<WeeklyBatch[]> {
    return apiClient.request("/admin/weekly-batches", { token });
  },

  async createWeeklyBatch(token: string, payload: { theater_id: number; week_start: string }): Promise<WeeklyBatch> {
    return apiClient.request("/admin/weekly-batches", { method: "POST", token, body: payload });
  },

  async getWeeklyBatch(token: string, batchId: number): Promise<WeeklyBatch> {
    return apiClient.request(`/admin/weekly-batches/${batchId}`, { token });
  },

  async updateWeeklyBatchStatus(token: string, batchId: number, status: "draft" | "ready"): Promise<WeeklyBatch> {
    return apiClient.request(`/admin/weekly-batches/${batchId}/status`, { method: "PATCH", token, body: { status } });
  },

  async parseImportDraft(token: string, batchId: number, rawText: string): Promise<ImportDraft> {
    return apiClient.request(`/admin/import-drafts/parse?batch_id=${batchId}`, { method: "POST", token, body: { raw_text: rawText } });
  },

  async getImportDraft(token: string, draftId: number): Promise<ImportDraft> {
    return apiClient.request(`/admin/import-drafts/${draftId}`, { token });
  },

  async getImportDrafts(token: string, batchId: number): Promise<ImportDraft[]> {
    return apiClient.request(`/admin/import-drafts?batch_id=${batchId}`, { token });
  },

  async createManualItem(token: string, draftId: number, payload: any): Promise<ImportDraftItem> {
    return apiClient.request(`/admin/import-drafts/${draftId}/items`, { method: "POST", token, body: payload });
  },

  async updateDraftItem(token: string, itemId: number, payload: any): Promise<ImportDraftItem> {
    return apiClient.request(`/admin/import-draft-items/${itemId}`, { method: "PATCH", token, body: payload });
  },

  async confirmDraftItem(token: string, itemId: number): Promise<ImportDraftItem> {
    return apiClient.request(`/admin/import-draft-items/${itemId}/confirm`, { method: "POST", token, body: {} });
  },

  async confirmValidItems(token: string, draftId: number): Promise<{ item_id: number; success: boolean; designation_id?: number; wish_id?: number; error?: string }[]> {
    return apiClient.request(`/admin/import-drafts/${draftId}/confirm-valid`, { method: "POST", token, body: {} });
  },

  async getBatchSchedulingInputs(token: string, batchId: number): Promise<BatchSchedulingInputs> {
    return apiClient.request(`/admin/weekly-batches/${batchId}/scheduling-inputs`, { token });
  },

  async updateActor(token: string, actorId: number, payload: Omit<Actor, "id" | "display_name" | "role_ids">): Promise<Actor> {
    return apiClient.request(`/admin/actors/${actorId}`, { method: "PATCH", token, body: payload });
  },

  async replaceActorCapabilities(token: string, actorId: number, roleIds: number[]): Promise<Actor> {
    return apiClient.request(`/admin/actors/${actorId}/capabilities`, { method: "PUT", token, body: { role_ids: roleIds } });
  },

  async getWeeklyScheduleWorkspace(token: string, theaterId: number, weekStart: string): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request(`/admin/weekly-schedules/workspace?theater_id=${theaterId}&week_start=${weekStart}`, { token });
  },

  async recommendWeeklySchedule(token: string, payload: ScheduleMutation): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request("/admin/weekly-schedules/recommend", { method: "POST", token, body: payload });
  },

  async validateWeeklySchedule(token: string, payload: ScheduleMutation): Promise<{ conflicts: ScheduleConflict[]; warnings: ScheduleConflict[]; empty_slots: { performance_id: number; role_id: number }[] }> {
    return apiClient.request("/admin/weekly-schedules/validate", { method: "POST", token, body: payload });
  },

  async saveWeeklyScheduleDraft(token: string, payload: ScheduleMutation): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request("/admin/weekly-schedules/draft", { method: "PUT", token, body: payload });
  },

  async publishWeeklySchedule(token: string, payload: ScheduleMutation): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request("/admin/weekly-schedules/publish", { method: "POST", token, body: payload });
  },
};

export const actorApi = {
  async getSchedule(token: string): Promise<any[]> {
    return apiClient.request("/actor/me/schedule", { token });
  },
  async submitLeave(token: string, payload: { dates: string[]; note?: string | null }): Promise<any> {
    return apiClient.request("/actor/me/leave-requests", { method: "POST", token, body: payload });
  },
};
