export type TopThreeGrantDefaults = {
  source_type: string;
  source_label: string;
  source_month: string;
  grant_date: string;
  default_expiry: string;
};

export type CardOperationResult = {
  actorId: number;
  actorName: string;
  outcome: "granted" | "saved" | "skipped" | "failed";
  reason?: string;
};

export type TopThreeActorCardExpose = {
  hasContent: () => boolean;
  isValid: () => boolean;
  saveDraft: () => Promise<CardOperationResult>;
  confirmGrant: () => Promise<CardOperationResult>;
};

export function summarizeCardResults(results: CardOperationResult[]) {
  return {
    successful: results.filter(item => item.outcome === "saved" || item.outcome === "granted").map(item => item.actorName),
    skipped: results.filter(item => item.outcome === "skipped").map(item => `${item.actorName}（${item.reason ?? "未满足条件"}）`),
    failed: results.filter(item => item.outcome === "failed").map(item => `${item.actorName}（${item.reason ?? "未知错误"}）`),
  };
}
