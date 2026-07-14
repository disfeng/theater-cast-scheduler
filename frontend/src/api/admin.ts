import { apiClient } from "./client";

export type Theater = { id: number; name: string; default_weekly_template: Record<string, string[]> };
export type Role = { id: number; name: string; group_name: string | null };
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
  slot: string;
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

export const adminApi = {
  async getTheaters(token: string): Promise<Theater[]> {
    return apiClient.request("/admin/theaters", { token });
  },

  async createTheater(token: string, payload: { name: string; default_weekly_template: Record<string, string[]> }): Promise<Theater> {
    return apiClient.request("/admin/theaters", { method: "POST", token, body: payload });
  },

  async getRoles(token: string): Promise<Role[]> {
    return apiClient.request("/admin/roles", { token });
  },

  async createRole(token: string, payload: { name: string; group_name: string | null }): Promise<Role> {
    return apiClient.request("/admin/roles", { method: "POST", token, body: payload });
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

  async getPerformances(token: string, theaterId: number, year: number, month: number): Promise<Performance[]> {
    return apiClient.request(`/admin/performances?theater_id=${theaterId}&year=${year}&month=${month}`, { token });
  },

  async createPerformance(token: string, payload: { theater_id: number; performance_date: string; slot: string }): Promise<Performance> {
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
};
