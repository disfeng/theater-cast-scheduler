export type BoardItemKind = "player" | "designation" | "wish" | "unresolved";
export type BoardChangeType = "added" | "modified" | "removed" | "unchanged";
export type BoardValidationStatus = "valid" | "ambiguous" | "invalid";

export type BoardCandidate = { field: string; id: number; label: string };
export type BoardDraftItemPatch = {
  item_kind?: BoardItemKind | null;
  player_name?: string | null; player_character_name?: string | null; paired_role_name?: string | null;
  relation_label?: string | null; theater_visit_ordinal?: number | null; character_visit_ordinal?: number | null;
  matched_player_id?: number | null; actor_id?: number | null; role_id?: number | null; note?: string | null;
  removal_lifecycle_confirmed?: boolean;
};
export type BoardDraftItem = BoardDraftItemPatch & {
  id: number; revision_id: number; item_kind: BoardItemKind; change_type: BoardChangeType;
  raw_line: string | null; actor_name_raw?: string | null; role_name_raw?: string | null;
  candidates?: BoardCandidate[] | null; confidence?: Record<string, number> | null;
  validation_status: BoardValidationStatus; failure_reason: string | null; confirmed_at: string | null;
  performance_player_id?: number | null; wish_id?: number | null;
};
export type BoardRevision = {
  id: number; board_id: number; revision_number: number; raw_text: string;
  status: "review_required" | "confirmed" | "failed"; parser_type: "deterministic" | "ai";
  created_at: string; confirmed_at: string | null; rollback_source_revision_id: number | null;
  draft_items: BoardDraftItem[];
};
export type PerformanceBoard = { id: number; performance_id: number; current_revision_id: number | null; revisions: BoardRevision[] };
