export type PlayerProfile = { id: number; display_name: string; normalized_name: string; status: "active" | "provisional" | "inactive" | "merged" };
export type ItemCategory = "designation" | "general";
export type DesignationBinding = "universal" | "top_three" | "paired";
export type EntitlementItemType = {
  id: number; theater_id: number; code: string; display_name: string;
  category: ItemCategory; designation_type: DesignationBinding | null;
  priority: number; default_validity_days: number; color: string; icon: string | null;
  description: string | null; is_active: boolean; sort_order: number;
  default_validity_months?: number;
};
export type GrantDraftItem = { id?: number; player_id: number; item_type_id: number; quantity?: number; source_month: string | null; source_label: string | null; expires_at: string | null; notes: string | null; bound_actor_id: number | null };
export type GrantBatchPayload = { source_type?: string; source_month: string | null; source_label: string; title: string | null; grant_date: string | null; default_expires_at: string | null; notes: string | null; bound_actor_id: number | null; items: GrantDraftItem[] };
export type GrantBatch = Omit<GrantBatchPayload, "items"> & { id: number; theater_id: number; status: "draft" | "granted" | "cancelled"; created_at: string; confirmed_at: string | null; draft_items: GrantDraftItem[] };
export type LedgerEntry = { id: number; event_type: string; occurred_at: string; from_status: string | null; to_status: string | null; performance_id: number | null; designation_id: number | null; reason: string | null; purpose?: string | null; operator_user_id: number | null };
export type EntitlementItem = { id: number; theater_id: number; serial_number: string; owner_id: number; item_type_id: number; source_type: string; source_month: string | null; source_label: string; granted_at: string; expires_at: string; status: string; current_designation_id: number | null; notes: string | null; bound_actor_id: number | null; bound_actor_name?: string | null; ledger_entries: LedgerEntry[] };
export type PlayerInventory = { player: PlayerProfile; items: EntitlementItem[] };
export type EntitlementLedgerRecord = { id: number; item_id: number; serial_number: string; player_id: number; player_name: string; item_type_id: number; item_type_name: string; bound_actor_id: number | null; bound_actor_name: string | null; event_type: string; occurred_at: string; from_status: string | null; to_status: string | null; purpose: string | null; reason: string | null; note: string | null; performance_id: number | null; designation_id: number | null };
export type EntitlementLedgerPage = { records: EntitlementLedgerRecord[]; next_cursor: number | null };
