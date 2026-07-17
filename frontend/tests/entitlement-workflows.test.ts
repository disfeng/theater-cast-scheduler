import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/vue";
import { renderAdminRoute } from "./helpers/render-app";
import { entitlementLabel, formatEntitlementDate, toIsoEndOfDay } from "../src/features/entitlements/format";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

test("核对面板显示失败、切换到期筛选并分页下钻道具流水", async () => {
  const paths: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    paths.push(path);
    if (path === "/admin/theaters" || path === "/admin/actors" || path === "/admin/roles") return Response.json([]);
    if (path === "/admin/entitlement-item-types" || path === "/admin/entitlement-grant-batches") return Response.json([]);
    if (path.includes("expiry=expires_within_7_days")) return Response.json({ detail: "audit unavailable" }, { status: 503 });
    if (path.startsWith("/admin/entitlements/reconciliation/drill")) return Response.json({
      kind: "items", total: 1, limit: 50, next_cursor: null,
      records: [{ id: 9, serial_number: "AUDIT-9", status: "available" }],
    });
    if (path === "/admin/entitlements/reconciliation") return Response.json({
      generated_at: "2026-07-17T00:00:00", expiry_filter: null,
      filtered_totals: { available: 1 }, global_totals: { available: 1 }, anomaly_count: 1,
      rows: [{ item_type: "universal", source_month: "2026-07-01", source_label: "July",
        player_id: 7, player_name: "兹", status: "available", item_count: 1,
        drill_down_filter: { item_type: "universal", source_month: "2026-07-01",
          source_label: "July", player_id: 7, status: "available" } }],
    });
    return Response.json({ detail: `unexpected:${path}` }, { status: 500 });
  }));
  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "权益流水核对" }));
  expect(await screen.findByText("筛选范围 1 张")).toBeInTheDocument();
  await fireEvent.click(await screen.findByRole("button", { name: "道具" }));
  expect(await screen.findByText(/AUDIT-9/)).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("radio", { name: "7 天内到期" }));
  expect(await screen.findByText("audit unavailable")).toBeInTheDocument();
  expect(paths.some((path) => path.includes("expiry=expires_within_7_days"))).toBe(true);
});

test("管理员按月发放三张独立权益并在玩家背包查看流水", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  const player = { id: 7, display_name: "兹", normalized_name: "兹", status: "active" };
  const itemType = { id: 3, code: "top_three", display_name: "前三指定", priority: 20, default_validity_months: 3 };
  let batch: any = {
    id: 41,
    source_month: "2026-04-01",
    source_label: "2026 年 4 月月度发放",
    title: "2026 年 4 月权益",
    grant_date: null,
    default_expires_at: null,
    notes: null,
    status: "draft",
    created_at: "2026-04-30T10:00:00Z",
    confirmed_at: null,
    draft_items: [],
  };

  const inventory = {
    player,
    items: [1, 2, 3].map((id) => ({
      id: 100 + id,
      serial_number: `TOP3-202604-${id}`,
      owner_id: 7,
      item_type_id: 3,
      source_month: "2026-04-01",
      source_label: [`四月榜单第一张`, `四月榜单第二张`, `四月榜单第三张`][id - 1],
      granted_at: "2026-04-30T10:05:00Z",
      expires_at: [`2026-07-01T00:00:00Z`, `2026-08-01T00:00:00Z`, `2026-09-01T00:00:00Z`][id - 1],
      status: "available",
      current_designation_id: null,
      notes: null,
      ledger_entries: [{ id: 200 + id, event_type: "granted", occurred_at: "2026-04-30T10:05:00Z", from_status: null, to_status: "available", performance_id: null, designation_id: null, reason: "月度发放", operator_user_id: 1 }],
    })),
  };

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    if (method !== "GET") requests.push({ method, path, body });

    if (path === "/admin/theaters" || path === "/admin/actors" || path === "/admin/roles") return Response.json([]);
    if (path === "/admin/entitlement-item-types") return Response.json([itemType]);
    if (path === "/admin/entitlement-grant-batches" && method === "GET") return Response.json([batch]);
    if (path === "/admin/entitlement-grant-batches" && method === "POST") return Response.json(batch);
    if (path === "/admin/entitlement-grant-batches/41" && method === "PATCH") {
      batch = {
        ...batch,
        ...body,
        draft_items: body.items.flatMap((item: any, index: number) =>
          Array.from({ length: item.quantity }, (_, offset) => ({ ...item, id: 501 + index + offset, quantity: undefined })),
        ),
      };
      return Response.json(batch);
    }
    if (path === "/admin/entitlement-grant-batches/41/confirm" && method === "POST") {
      batch = { ...batch, status: "granted", confirmed_at: "2026-04-30T10:05:00Z" };
      return Response.json(batch);
    }
    if (path === "/admin/player-profiles?q=%E5%85%B9") return Response.json([player]);
    if (path === "/admin/players/7/inventory") return Response.json(inventory);
    const mutation = path.match(/^\/admin\/entitlement-items\/(\d+)\/(extend|void|restore)$/);
    if (mutation && method === "POST") {
      const item = inventory.items.find((entry) => entry.id === Number(mutation[1]))!;
      if (mutation[2] === "void") item.status = "revoked";
      if (mutation[2] === "restore") item.status = "available";
      if (mutation[2] === "extend") item.expires_at = body.expires_at;
      return Response.json(item);
    }
    return Response.json({ detail: `unexpected_request:${method}:${path}` }, { status: 500 });
  }));

  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "月度发放" }));
  await fireEvent.update(screen.getByLabelText("来源月份"), "2026-04");
  await fireEvent.click(screen.getByRole("button", { name: "创建草稿" }));

  await fireEvent.update(await screen.findByLabelText("玩家搜索"), "兹");
  await fireEvent.click(await screen.findByRole("button", { name: "选择玩家 兹" }));
  await fireEvent.update(screen.getByLabelText("权益数量"), "3");
  await fireEvent.click(screen.getByRole("button", { name: "添加权益" }));

  const rows = screen.getAllByTestId("grant-item-card");
  expect(rows).toHaveLength(3);
  for (const [index, row] of rows.entries()) {
    await fireEvent.update(within(row).getByLabelText("权益来源"), `四月榜单第${["一", "二", "三"][index]}张`);
    await fireEvent.update(within(row).getByLabelText("到期日期"), `2026-0${7 + index}-01`);
  }
  await fireEvent.click(screen.getByRole("button", { name: "确认发放" }));
  await fireEvent.click(await screen.findByRole("button", { name: "确认" }));
  await screen.findByText("已确认，只读");
  const patchRequest = requests.find((request) => request.method === "PATCH" && request.path === "/admin/entitlement-grant-batches/41");
  expect(patchRequest?.body.items).toEqual([
    { player_id: 7, item_type_id: 3, quantity: 1, source_month: "2026-04-01", source_label: "四月榜单第一张", expires_at: "2026-07-01T23:59:59.999+08:00", notes: null },
    { player_id: 7, item_type_id: 3, quantity: 1, source_month: "2026-04-01", source_label: "四月榜单第二张", expires_at: "2026-08-01T23:59:59.999+08:00", notes: null },
    { player_id: 7, item_type_id: 3, quantity: 1, source_month: "2026-04-01", source_label: "四月榜单第三张", expires_at: "2026-09-01T23:59:59.999+08:00", notes: null },
  ]);
  expect(requests.findIndex((request) => request.method === "PATCH")).toBeLessThan(requests.findIndex((request) => request.path.endsWith("/confirm")));
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
  expect(screen.getAllByLabelText("权益来源").every((input) => input.hasAttribute("disabled"))).toBe(true);

  await fireEvent.click(screen.getByRole("tab", { name: "权益背包" }));
  await fireEvent.update(screen.getByLabelText("搜索玩家权益"), "兹");
  await fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  await fireEvent.click(await screen.findByRole("button", { name: "查看 兹 的权益" }));

  expect(await screen.findAllByTestId("inventory-item-card")).toHaveLength(3);
  expect(screen.getAllByText("已发放")).toHaveLength(3);
  expect(screen.getByText("TOP3-202604-1")).toBeInTheDocument();
  expect(screen.getByText("TOP3-202604-2")).toBeInTheDocument();
  expect(screen.getByText("TOP3-202604-3")).toBeInTheDocument();

  await fireEvent.click(within(screen.getAllByTestId("inventory-item-card")[0]).getByRole("button", { name: "作废" }));
  expect((await screen.findAllByText(/TOP3-202604-1/)).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText(/作废后该权益将不可用于指定/)).toBeInTheDocument();
  await fireEvent.update(screen.getByLabelText("操作原因"), "重复发放");
  await fireEvent.click(screen.getByRole("button", { name: "确认作废" }));
  await waitFor(() => expect(requests).toContainEqual({ method: "POST", path: "/admin/entitlement-items/101/void", body: { reason: "重复发放" } }));
  await fireEvent.click(await screen.findByRole("button", { name: "恢复" }));
  await fireEvent.update(screen.getByLabelText("操作原因"), "核对无误");
  await fireEvent.click(screen.getByRole("button", { name: "确认恢复" }));
  await waitFor(() => expect(requests).toContainEqual({ method: "POST", path: "/admin/entitlement-items/101/restore", body: { reason: "核对无误" } }));
  await waitFor(() => expect(within(screen.getAllByTestId("inventory-item-card")[0]).getByRole("button", { name: "延期" })).toBeEnabled());
  await fireEvent.click(within(screen.getAllByTestId("inventory-item-card")[0]).getByRole("button", { name: "延期" }));
  expect(screen.getByText(/原到期日/)).toBeInTheDocument();
  await fireEvent.update(screen.getByLabelText("新到期日"), "2026-10-01");
  await fireEvent.update(screen.getByLabelText("操作原因"), "活动顺延");
  await fireEvent.click(screen.getByRole("button", { name: "确认延期" }));
  await waitFor(() => expect(requests).toContainEqual({ method: "POST", path: "/admin/entitlement-items/101/extend", body: { expires_at: "2026-10-01T23:59:59.999+08:00", reason: "活动顺延" } }));
});

test("业务日期选择日与中文回显保持同一天", () => {
  const iso = toIsoEndOfDay("2026-07-01")!;
  expect(formatEntitlementDate(iso)).toBe("2026年7月1日");
});

test("完整中文化后端权益状态与流水事件并清晰回退未知值", () => {
  expect(["available", "reserved", "consumed", "expired", "revoked"].map(entitlementLabel)).toEqual(["可用", "已预留", "已核销", "已过期", "已撤销"]);
  expect(["granted", "reserved", "released", "consumed", "expired", "revoked", "extended", "restored", "adjusted"].map(entitlementLabel)).toEqual(["已发放", "已预留", "已释放", "已核销", "已过期", "已撤销", "已延期", "已恢复", "已调整"]);
  expect(entitlementLabel("future_status")).toBe("未知状态（future_status）");
});

test("页面加载已有草稿并可选择回填独立条目，已确认批次只读", async () => {
  const draft = { id: 8, source_month: "2026-03-01", source_label: "三月发放", title: "三月批次", grant_date: null, default_expires_at: null, notes: null, status: "draft", created_at: "2026-03-31T00:00:00Z", confirmed_at: null, draft_items: [{ id: 80, player_id: 2, item_type_id: 3, source_month: "2026-03-01", source_label: "三月第一张", expires_at: "2026-06-30T15:59:59.999Z", notes: null }] };
  const confirmed = { ...draft, id: 9, title: "二月已确认", source_month: "2026-02-01", status: "granted", confirmed_at: "2026-02-28T00:00:00Z" };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, ""); const method = init?.method ?? "GET";
    if (["/admin/theaters", "/admin/actors", "/admin/roles"].includes(path)) return Response.json([]);
    if (path === "/admin/entitlement-item-types") return Response.json([{ id: 3, code: "top_three", display_name: "前三指定", priority: 1, default_validity_months: 3 }]);
    if (path === "/admin/entitlement-grant-batches" && method === "GET") return Response.json([draft, confirmed]);
    return Response.json({ detail: `unexpected_request:${method}:${path}` }, { status: 500 });
  }));
  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "月度发放" }));
  await fireEvent.click(await screen.findByRole("button", { name: "打开批次 三月批次" }));
  expect(await screen.findByDisplayValue("三月第一张")).toBeEnabled();
  await fireEvent.click(screen.getByRole("button", { name: "打开批次 二月已确认" }));
  expect(await screen.findByText("已确认，只读")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
});

test("玩家搜索区分加载中与无结果并防止重复提交", async () => {
  let release!: (response: Response) => void;
  const deferred = new Promise<Response>((resolve) => { release = resolve; });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (["/admin/theaters", "/admin/actors", "/admin/roles"].includes(path)) return Response.json([]);
    if (path === "/admin/entitlement-item-types") return Response.json([]);
    if (path === "/admin/player-profiles?q=%E4%B8%8D%E5%AD%98%E5%9C%A8") return deferred;
    return Response.json({ detail: `unexpected_request:GET:${path}` }, { status: 500 });
  }));
  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "权益背包" }));
  await fireEvent.update(await screen.findByLabelText("搜索玩家权益"), "不存在");
  await fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  expect(await screen.findByRole("status")).toHaveTextContent("正在搜索玩家");
  expect(screen.getByRole("button", { name: "搜索" })).toBeDisabled();
  release(Response.json([]));
  expect(await screen.findByText("未找到匹配玩家")).toBeInTheDocument();
});

test("发放玩家搜索只采用最新查询结果，慢响应不能覆盖快响应", async () => {
  let releaseSlow!: (response: Response) => void;
  const slow = new Promise<Response>((resolve) => { releaseSlow = resolve; });
  const draft = { id: 11, source_month: "2026-04-01", source_label: "四月", title: "竞态测试", grant_date: null, default_expires_at: null, notes: null, status: "draft", created_at: "2026-04-01T00:00:00Z", confirmed_at: null, draft_items: [] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (["/admin/theaters", "/admin/actors", "/admin/roles"].includes(path)) return Response.json([]);
    if (path === "/admin/entitlement-item-types") return Response.json([]);
    if (path === "/admin/entitlement-grant-batches") return Response.json([draft]);
    if (path === "/admin/player-profiles?q=a") return slow;
    if (path === "/admin/player-profiles?q=alice") return Response.json([{ id: 2, display_name: "Alice", normalized_name: "alice", status: "active" }]);
    return Response.json({ detail: `unexpected_request:GET:${path}` }, { status: 500 });
  }));
  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "月度发放" }));
  await fireEvent.click(await screen.findByRole("button", { name: "打开批次 竞态测试" }));
  const input = screen.getByLabelText("玩家搜索");
  await fireEvent.update(input, "a");
  await new Promise((resolve) => setTimeout(resolve, 320));
  await fireEvent.update(input, "alice");
  expect(await screen.findByRole("button", { name: "选择玩家 Alice" })).toBeInTheDocument();
  releaseSlow(Response.json([{ id: 1, display_name: "旧结果", normalized_name: "old", status: "active" }]));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.queryByRole("button", { name: "选择玩家 旧结果" })).not.toBeInTheDocument();
});

test("确认前保存失败时不会发送 confirm 请求", async () => {
  let confirmRequests = 0;
  const draft = { id: 12, source_month: "2026-05-01", source_label: "五月", title: "保存失败测试", grant_date: null, default_expires_at: null, notes: null, status: "draft", created_at: "2026-05-01T00:00:00Z", confirmed_at: null, draft_items: [{ id: 120, player_id: 2, item_type_id: 3, source_month: "2026-05-01", source_label: "五月权益", expires_at: "2026-08-01T15:59:59.999Z", notes: null }] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, ""); const method = init?.method ?? "GET";
    if (["/admin/theaters", "/admin/actors", "/admin/roles"].includes(path)) return Response.json([]);
    if (path === "/admin/entitlement-item-types") return Response.json([{ id: 3, code: "top_three", display_name: "前三指定", priority: 1, default_validity_months: 3 }]);
    if (path === "/admin/entitlement-grant-batches" && method === "GET") return Response.json([draft]);
    if (path === "/admin/entitlement-grant-batches/12" && method === "PATCH") return Response.json({ detail: "草稿保存失败" }, { status: 500 });
    if (path.endsWith("/confirm")) { confirmRequests += 1; return Response.json(draft); }
    return Response.json({ detail: `unexpected_request:${method}:${path}` }, { status: 500 });
  }));
  renderAdminRoute("/admin/entitlements");
  await fireEvent.click(await screen.findByRole("tab", { name: "月度发放" }));
  await fireEvent.click(await screen.findByRole("button", { name: "打开批次 保存失败测试" }));
  await fireEvent.click(screen.getByRole("button", { name: "确认发放" }));
  await fireEvent.click(await screen.findByRole("button", { name: "确认" }));
  expect(await screen.findByText("草稿保存失败")).toBeInTheDocument();
  expect(confirmRequests).toBe(0);
});
