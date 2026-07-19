const labels: Record<string, string> = { available: "可用", reserved: "已预留", consumed: "已核销", manually_consumed: "手工核销", expired: "已过期", revoked: "已撤销", granted: "已发放", released: "已释放", extended: "已延期", restored: "已恢复", adjusted: "已调整", none: "—" };
export const entitlementLabel = (value: string) => labels[value] ?? `未知状态（${value}）`;
export const formatEntitlementDate = (value: string | null) => value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeZone: "Asia/Shanghai" }).format(new Date(value)) : "—";
export const monthStart = (month: string) => `${month}-01`;
export const toIsoEndOfDay = (date: string) => date ? `${date}T23:59:59.999+08:00` : null;
export const businessDateInput = (value: string | null) => value ? new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Shanghai" }).format(new Date(value)) : "";

type LedgerSummarySource = {
  purpose: string | null;
  reason: string | null;
  note: string | null;
};

const ledgerBusinessFields = ["purpose", "reason", "note"] as const;

export function formatLedgerSummary(source: LedgerSummarySource): string {
  for (const value of [source.purpose, source.reason, source.note]) {
    const text = value?.trim();
    if (!text) continue;
    if (!text.startsWith("{") && !text.startsWith("[")) return text;
    try {
      const payload = JSON.parse(text);
      if (!payload || Array.isArray(payload) || typeof payload !== "object") continue;
      for (const field of ledgerBusinessFields) {
        const summary = payload[field];
        if (typeof summary === "string" && summary.trim()) return summary.trim();
      }
    } catch {
      return "操作记录";
    }
  }
  return "系统操作";
}
