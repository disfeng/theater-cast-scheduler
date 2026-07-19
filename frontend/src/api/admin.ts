import { apiClient } from "./client";
import type { EntitlementItem, EntitlementItemType, EntitlementLedgerPage, GrantBatch, GrantBatchPayload, PlayerInventory, PlayerProfile } from "../features/entitlements/types";
import type { BoardDraftItem, BoardDraftItemPatch, BoardRevision, PerformanceBoard } from "../features/performance-board/types";
import type { DesignationMonthWorkspace, PerformanceWorkspace } from "../features/designation-workspace/types";

export type Theater = { id: number; name: string; is_active: boolean };
export type AiParserSettings = { enabled: boolean; endpoint: string; api_key_masked: string | null; model_name: string; timeout_seconds: number; prompt_version: string; last_test_ok: boolean | null; last_test_message: string | null; last_tested_at: string | null };
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
  locked?: boolean; designation_id?: number | null; designation_type?: "universal" | "top_three" | "paired" | null;
  owner_player_name?: string | null; beneficiary_player_name?: string | null;
  entitlement_serial?: string | null; legacy_identity_fallback?: boolean;
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
  theater_id: number; week_start: string; expected_version: number; assignments: ScheduleAssignment[];
  context_weeks?: ScheduleWeekContext[]; confirm_conflicts?: boolean;
  confirmation_token?: string; idempotency_key?: string;
};
export type ScheduleWeekContext = { week_start: string; assignments: ScheduleAssignment[] };
export type ScheduleValidationResult = {
  conflicts: ScheduleConflict[]; warnings: ScheduleConflict[];
  empty_slots: { performance_id: number; role_id: number }[];
};
export type Predesignation = {
  id: number; version: number; usage_type: "self" | "proxy" | null; lifecycle_status: string | null;
  verification_status: string | null; failure_reason: string | null; verification_note: string | null;
  verified_at: string | null; verified_by: number | null; verifier_name: string | null;
  performance_id: number | null; performance_label: string | null;
  beneficiary_performance_player_id: number | null; beneficiary_player_id: number | null; beneficiary_name: string;
  owner_player_id: number | null; owner_name: string | null; designation_type: "universal" | "top_three" | "paired";
  priority: number; actor_id: number; actor_name: string; role_id: number; role_name: string;
  entitlement_item_id: number | null; entitlement_serial: string | null; entitlement_source: string | null; entitlement_expiry: string | null;
  available_items: { id: number; serial_number: string; source_label: string; expires_at: string; status: string }[];
  conflict: { id: number; designation_type: string; version: number; priority: number } | null;
  comparison: "higher" | "lower" | "equal" | null; outcome: string; action: string;
  status_history: { event: string; at: string; from_status: string | null; to_status: string | null; item_id?: number | null; conflict_designation_id?: number | null; note?: string | null; operator_user_id: number }[];
};

export type PerformanceWish = {
  id: number; performance_id: number; performance_player_id: number; player_name: string;
  actor_id: number; actor_name: string; role_id: number; role_name: string;
  note: string | null; status: "active" | "accepted" | "cancelled"; failure_reason: string | null;
  version: number;
};
export type EntitlementReconciliation = {
  generated_at: string; expiry_filter: string | null; filtered_totals: Record<string, number>;
  global_totals: Record<string, number>; anomaly_count: number;
  rows: { item_type: string; source_month: string; source_label: string; player_id: number;
    player_name: string; status: string; item_count: number;
    drill_down_filter: Record<string, string | number> }[];
};
export type ReconciliationDrill = { kind: string; total: number; limit: number;
  next_cursor: number | null; records: Record<string, any>[] };
const mutationKey = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;

export const adminApi = {
  async getDesignationMonthWorkspace(token: string, theaterId: number, year: number, month: number): Promise<DesignationMonthWorkspace> {
    return apiClient.request(`/admin/designation-workspace/month?theater_id=${theaterId}&year=${year}&month=${month}`, { token });
  },
  async getPerformanceReviewWorkspace(token: string, performanceId: number): Promise<PerformanceWorkspace> {
    return apiClient.request(`/admin/designation-workspace/performances/${performanceId}`, { token });
  },
  async getEntitlementReconciliation(token: string, expiry?: string): Promise<EntitlementReconciliation> {
    return apiClient.request(`/admin/entitlements/reconciliation${expiry ? `?expiry=${expiry}` : ""}`, { token });
  },
  async getEntitlementReconciliationDrill(token: string, kind: string, expiry?: string,
    filters: Record<string, string | number> = {}, cursor = 0): Promise<ReconciliationDrill> {
    const query = new URLSearchParams({ kind, limit: "50", cursor: String(cursor) });
    if (expiry) query.set("expiry", expiry);
    Object.entries(filters).forEach(([key, value]) => query.set(key, String(value)));
    return apiClient.request(`/admin/entitlements/reconciliation/drill?${query}`, { token });
  },
  async getDesignations(token: string): Promise<Predesignation[]> { return apiClient.request("/admin/designations", { token }); },
  async getWishes(token: string, performanceId?: number): Promise<PerformanceWish[]> { return apiClient.request(`/admin/wishes${performanceId ? `?performance_id=${performanceId}` : ""}`, { token }); },
  async createWish(token: string, payload: { performance_id: number; performance_player_id: number; actor_id: number; role_id: number; note?: string | null }): Promise<PerformanceWish> { return apiClient.request("/admin/wishes", { method: "POST", token, body: { ...payload, expected_version: 0, idempotency_key: mutationKey() } }); },
  async cancelWish(token: string, row: PerformanceWish, reason: string): Promise<PerformanceWish> { return apiClient.request(`/admin/wishes/${row.id}/cancel`, { method: "POST", token, body: { reason, expected_version: row.version, idempotency_key: mutationKey() } }); },
  async acceptWish(token: string, row: PerformanceWish, note?: string): Promise<PerformanceWish> { return apiClient.request(`/admin/wishes/${row.id}/accept`, { method: "POST", token, body: { note: note || null, expected_version: row.version, idempotency_key: mutationKey() } }); },
  async verifyProxyDesignation(token: string, row: Predesignation, payload: { owner_player_id: number; item_id: number; note: string }): Promise<Predesignation> { return apiClient.request(`/admin/designations/${row.id}/verify-proxy`, { method: "POST", token, body: { ...payload, expected_version: row.version, idempotency_key: mutationKey() } }); },
  async activateDesignation(token: string, row: Predesignation, itemId: number): Promise<Predesignation> { return apiClient.request(`/admin/designations/${row.id}/activate`, { method: "POST", token, body: { item_id: itemId, expected_version: row.version, idempotency_key: mutationKey() } }); },
  async replaceDesignation(token: string, incoming: Predesignation): Promise<Predesignation> { return apiClient.request(`/admin/designations/${incoming.id}/replace`, { method: "POST", token, body: { replaced_id: incoming.conflict!.id, expected_versions: { incoming: incoming.version, replaced: incoming.conflict!.version }, confirmed: true, idempotency_key: mutationKey() } }); },
  async cancelDesignation(token: string, row: Predesignation, reason: string): Promise<Predesignation> { return apiClient.request(`/admin/designations/${row.id}/cancel`, { method: "POST", token, body: { reason, expected_version: row.version, idempotency_key: mutationKey() } }); },
  async resolveEqualDesignation(token:string,row:Predesignation,decision:"choose_incoming"|"keep_occupied"):Promise<Predesignation>{return apiClient.request(`/admin/designations/${row.id}/resolve-equal`,{method:"POST",token,body:{occupied_id:row.conflict!.id,decision,expected_versions:{incoming:row.version,occupied:row.conflict!.version},confirmed:true,idempotency_key:mutationKey()}})},
  async getAiParserSettings(token: string): Promise<AiParserSettings> { return apiClient.request("/admin/system-settings/ai-parser", { token }); },
  async updateAiParserSettings(token: string, payload: { enabled: boolean; endpoint: string; api_key?: string; model_name: string; timeout_seconds: number }): Promise<AiParserSettings> { return apiClient.request("/admin/system-settings/ai-parser", { method: "PUT", token, body: payload }); },
  async testAiParserConnection(token: string): Promise<{ ok: boolean; message: string }> { return apiClient.request("/admin/system-settings/ai-parser/test", { method: "POST", token, body: {} }); },
  async getPerformanceBoard(token: string, performanceId: number, signal?: AbortSignal): Promise<PerformanceBoard> {
    return apiClient.request(`/admin/performances/${performanceId}/board`, { token, signal });
  },

  async createBoardRevision(token: string, performanceId: number, rawText: string, parseWithAi = true): Promise<BoardRevision> {
    return apiClient.request(`/admin/performances/${performanceId}/board/revisions`, { method: "POST", token, body: { raw_text: rawText, parse_with_ai: parseWithAi } });
  },

  async updateBoardDraftItem(token: string, itemId: number, patch: BoardDraftItemPatch): Promise<BoardDraftItem> {
    return apiClient.request(`/admin/board-draft-items/${itemId}`, { method: "PATCH", token, body: patch });
  },

  async confirmBoardDraftItem(token: string, itemId: number, patch: BoardDraftItemPatch = {}): Promise<BoardDraftItem> {
    return apiClient.request(`/admin/board-draft-items/${itemId}/confirm`, { method: "POST", token, body: patch });
  },
  async reopenBoardDraftItem(token: string, itemId: number): Promise<BoardDraftItem> {
    return apiClient.request(`/admin/board-draft-items/${itemId}/reopen`, { method: "POST", token });
  },

  async confirmValidBoardItems(token: string, revisionId: number): Promise<BoardRevision> {
    return apiClient.request(`/admin/board-revisions/${revisionId}/confirm-valid`, { method: "POST", token, body: {} });
  },

  async activateBoardRevision(token: string, revisionId: number): Promise<BoardRevision> {
    return apiClient.request(`/admin/board-revisions/${revisionId}/activate`, { method: "POST", token, body: {} });
  },

  async rollbackBoardRevision(token: string, revisionId: number): Promise<BoardRevision> {
    return apiClient.request(`/admin/board-revisions/${revisionId}/rollback`, { method: "POST", token, body: {} });
  },
  async getPlayerProfiles(token: string, query = "", signal?: AbortSignal): Promise<PlayerProfile[]> {
    return apiClient.request(`/admin/player-profiles?q=${encodeURIComponent(query)}`, { token, signal });
  },

  async updatePlayerProfile(token: string, playerId: number, payload: { status: "active" }): Promise<PlayerProfile> {
    return apiClient.request(`/admin/player-profiles/${playerId}`, { method: "PATCH", token, body: payload });
  },

  async getPlayerInventory(token: string, playerId: number): Promise<PlayerInventory> {
    return apiClient.request(`/admin/players/${playerId}/inventory`, { token });
  },

  async getEntitlementItemTypes(token: string): Promise<EntitlementItemType[]> {
    return apiClient.request("/admin/entitlement-item-types", { token });
  },

  async getTheaterEntitlementItemTypes(token: string, theaterId: number): Promise<EntitlementItemType[]> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-item-types`, { token });
  },

  async createEntitlementItemType(token: string, theaterId: number, payload: Omit<EntitlementItemType, "id" | "theater_id">): Promise<EntitlementItemType> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-item-types`, { method: "POST", token, body: payload });
  },

  async updateEntitlementItemType(token: string, typeId: number, payload: Partial<EntitlementItemType>): Promise<EntitlementItemType> {
    return apiClient.request(`/admin/entitlement-item-types/${typeId}`, { method: "PATCH", token, body: payload });
  },

  async createDefaultDesignationTypes(token: string, theaterId: number): Promise<EntitlementItemType[]> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-item-types/default-designations`, { method: "POST", token, body: {} });
  },

  async getTheaterGrantBatches(token: string, theaterId: number): Promise<GrantBatch[]> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-grant-batches`, { token });
  },

  async createTheaterGrantBatch(token: string, theaterId: number, payload: GrantBatchPayload): Promise<GrantBatch> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-grant-batches`, { method: "POST", token, body: payload });
  },

  async matchEntitlementGrantPlayers(token: string, theaterId: number, names: string[]): Promise<{ raw_name: string; player: PlayerProfile | null; candidates: PlayerProfile[]; created: boolean }[]> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-grant-player-matches`, { method: "POST", token, body: { names } });
  },

  async confirmTheaterGrantBatch(token: string, theaterId: number, batchId: number, key: string): Promise<GrantBatch> {
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-grant-batches/${batchId}/confirm`, { method: "POST", token, body: {}, headers: { "Idempotency-Key": key } });
  },

  async getTheaterPlayerInventory(token: string, theaterId: number, playerId: number): Promise<PlayerInventory> {
    return apiClient.request(`/admin/theaters/${theaterId}/players/${playerId}/inventory`, { token });
  },

  async previewManualConsumption(token: string, theaterId: number, playerId: number, payload: { item_type_id: number; quantity: number; purpose: string; note: string | null; performance_id: number | null }): Promise<{ item_ids: number[]; serial_numbers: string[] }> {
    return apiClient.request(`/admin/theaters/${theaterId}/players/${playerId}/inventory/manual-consumption/preview`, { method: "POST", token, body: payload });
  },

  async commitManualConsumption(token: string, theaterId: number, playerId: number, payload: { item_type_id: number; quantity: number; purpose: string; note: string | null; performance_id: number | null }, key: string): Promise<{ item_ids: number[]; serial_numbers: string[] }> {
    return apiClient.request(`/admin/theaters/${theaterId}/players/${playerId}/inventory/manual-consumption`, { method: "POST", token, body: payload, headers: { "Idempotency-Key": key } });
  },

  async getEntitlementLedger(token: string, theaterId: number, filters: Record<string, string | number | null | undefined> = {}): Promise<EntitlementLedgerPage> {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== null && value !== undefined && value !== "") query.set(key, String(value)); });
    return apiClient.request(`/admin/theaters/${theaterId}/entitlement-ledger${query.size ? `?${query}` : ""}`, { token });
  },

  async getGrantBatches(token: string): Promise<GrantBatch[]> {
    return apiClient.request("/admin/entitlement-grant-batches", { token });
  },

  async createGrantBatch(token: string, payload: GrantBatchPayload): Promise<GrantBatch> {
    return apiClient.request("/admin/entitlement-grant-batches", { method: "POST", token, body: payload });
  },

  async updateGrantBatch(token: string, batchId: number, payload: GrantBatchPayload): Promise<GrantBatch> {
    return apiClient.request(`/admin/entitlement-grant-batches/${batchId}`, { method: "PATCH", token, body: payload });
  },

  async confirmGrantBatch(token: string, batchId: number): Promise<GrantBatch> {
    return apiClient.request(`/admin/entitlement-grant-batches/${batchId}/confirm`, { method: "POST", token, body: {} });
  },

  async extendEntitlementItem(token: string, itemId: number, payload: { expires_at: string; reason: string }): Promise<EntitlementItem> {
    return apiClient.request(`/admin/entitlement-items/${itemId}/extend`, { method: "POST", token, body: payload });
  },

  async voidEntitlementItem(token: string, itemId: number, payload: { reason: string }): Promise<EntitlementItem> {
    return apiClient.request(`/admin/entitlement-items/${itemId}/void`, { method: "POST", token, body: payload });
  },

  async restoreEntitlementItem(token: string, itemId: number, payload: { reason: string }): Promise<EntitlementItem> {
    return apiClient.request(`/admin/entitlement-items/${itemId}/restore`, { method: "POST", token, body: payload });
  },
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

  async getPerformances(token: string, theaterId: number, year: number, month: number, signal?: AbortSignal): Promise<Performance[]> {
    return apiClient.request(`/admin/performances?theater_id=${theaterId}&year=${year}&month=${month}`, { token, signal });
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

  async validateScheduleContext(token: string, payload: { theater_id: number; weeks: ScheduleWeekContext[] }): Promise<ScheduleValidationResult> {
    return apiClient.request("/admin/weekly-schedules/validate-context", { method: "POST", token, body: payload });
  },

  async saveWeeklyScheduleDraft(token: string, payload: ScheduleMutation): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request("/admin/weekly-schedules/draft", { method: "PUT", token, body: payload });
  },

  async publishWeeklySchedule(token: string, payload: ScheduleMutation): Promise<WeeklyScheduleWorkspace> {
    return apiClient.request("/admin/weekly-schedules/publish", { method: "POST", token, body: { ...payload, idempotency_key: payload.idempotency_key || mutationKey() } });
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
