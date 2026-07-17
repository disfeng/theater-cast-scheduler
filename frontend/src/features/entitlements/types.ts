export type PlayerProfile = { id: number; display_name: string; normalized_name: string; status: "active" | "provisional" | "inactive" | "merged" };
export type EntitlementItemType = { id: number; code: string; display_name: string; priority: number; default_validity_months: number };
export type GrantDraftItem = { id?: number; player_id: number; item_type_id: number; quantity?: number; source_month: string | null; source_label: string | null; expires_at: string | null; notes: string | null };
export type GrantBatchPayload = { source_month: string; source_label: string; title: string | null; grant_date: string | null; default_expires_at: string | null; notes: string | null; items: GrantDraftItem[] };
export type GrantBatch = Omit<GrantBatchPayload, "items"> & { id: number; status: "draft" | "granted" | "cancelled"; created_at: string; confirmed_at: string | null; draft_items: GrantDraftItem[] };
export type LedgerEntry = { id: number; event_type: string; occurred_at: string; from_status: string | null; to_status: string | null; performance_id: number | null; designation_id: number | null; reason: string | null; operator_user_id: number | null };
export type EntitlementItem = { id: number; serial_number: string; owner_id: number; item_type_id: number; source_month: string; source_label: string; granted_at: string; expires_at: string; status: string; current_designation_id: number | null; notes: string | null; ledger_entries: LedgerEntry[] };
export type PlayerInventory = { player: PlayerProfile; items: EntitlementItem[] };
