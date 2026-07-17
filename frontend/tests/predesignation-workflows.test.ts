import { fireEvent, render, screen, waitFor, within } from "@testing-library/vue";
import ElementPlus from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, test, vi } from "vitest";
import PerformanceDesignationReview from "../src/components/admin/PerformanceDesignationReview.vue";

const pending: any = {
  id: 31, version: 1, usage_type: "proxy", lifecycle_status: "pending_verification", verification_status: "pending",
  failure_reason: "proxy_verification_required", verification_note: null, verified_at: null, verified_by: null, verifier_name: null,
  performance_id: 88, performance_label: "2026-07-19 晚场", beneficiary_performance_player_id: 7, beneficiary_player_id: 2,
  beneficiary_name: "使用玩家B", owner_player_id: null, owner_name: null, designation_type: "top_three", priority: 20,
  actor_id: 9, actor_name: "演员甲", role_id: 5, role_name: "角色乙", entitlement_item_id: null, entitlement_serial: null,
  entitlement_source: null, entitlement_expiry: null, available_items: [], conflict: null, comparison: null,
  outcome: "pending_verification", action: "none", status_history: [],
};

beforeEach(() => { localStorage.clear(); localStorage.setItem("token", "admin-token"); localStorage.setItem("role", "admin"); vi.restoreAllMocks(); });
function mount(rows: any[]) { const pinia = createPinia(); setActivePinia(pinia); return render(PerformanceDesignationReview, { props: { rows }, global: { plugins: [pinia, ElementPlus] } }); }

test("客服在当前场次核验代指定持有人并预占具体权益", async () => {
  const bodies: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path.includes("/admin/player-profiles")) return Response.json([{ id: 1, display_name: "持有人A", normalized_name: "a", status: "active" }]);
    if (path === "/admin/players/1/inventory") return Response.json({ player: { id: 1, display_name: "持有人A" }, items: [{ id: 101, serial_number: "TOP3-101", owner_id: 1, item_type_id: 2, source_label: "六月榜单", expires_at: "2026-08-01T00:00:00Z", status: "available" }] });
    if (path === "/admin/entitlement-item-types") return Response.json([{ id: 2, code: "top_three", display_name: "榜三" }]);
    if (path === "/admin/designations/31/verify-proxy") { bodies.push(JSON.parse(String(init?.body))); return Response.json({ ...pending, lifecycle_status: "predesignated" }); }
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount([{ ...pending }]);
  const card = screen.getByText("使用玩家B").closest("article")!;
  await fireEvent.update(within(card).getByLabelText("搜索权益持有人"), "持有人");
  await fireEvent.click(within(card).getByRole("button", { name: "搜索" }));
  await fireEvent.click(await within(card).findByRole("button", { name: "选择 持有人A" }));
  await fireEvent.update(within(card).getByLabelText("核验备注"), "已电话确认");
  const verifyButton = within(card).getByRole("button", { name: "确认代指定并预占" });
  await waitFor(() => expect(verifyButton).not.toBeDisabled());
  await fireEvent.click(verifyButton);
  await waitFor(() => expect(bodies[0]).toEqual(expect.objectContaining({ owner_player_id: 1, item_id: 101, note: "已电话确认", expected_version: 1 })));
});

test("高优先级替换必须二次确认", async () => {
  const row = { ...pending, id: 32, usage_type: "self", lifecycle_status: "pending_conflict", owner_name: "B", action: "confirm_replace", comparison: "higher", conflict: { id: 30, designation_type: "paired", version: 4, priority: 10 }, available_items: [{ id: 3, serial_number: "U-3", source_label: "六月", expires_at: "2026-09-01", status: "available" }] };
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => { calls.push(String(input)); return Response.json({ ...row, lifecycle_status: "predesignated" }); }));
  mount([row]);
  await fireEvent.click(screen.getByRole("button", { name: "替换低优先级指定" }));
  expect(await screen.findByText("替换后将释放原指定预占的权益，是否继续？")).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button", { name: "确认替换" }));
  await waitFor(() => expect(calls.some(path => path.endsWith("/admin/designations/32/replace"))).toBe(true));
});

test("同优先级可选择新指定", async () => {
  const row = { ...pending, id: 40, version: 3, usage_type: "self", owner_name: "B", lifecycle_status: "manual_review", action: "choose_manually", comparison: "equal", conflict: { id: 41, designation_type: "top_three", version: 5, priority: 20 } };
  const bodies: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return Response.json(row); }));
  mount([row]);
  await fireEvent.click(screen.getByRole("button", { name: "选择新指定" }));
  await fireEvent.click(await screen.findByRole("button", { name: "确认选择新指定" }));
  await waitFor(() => expect(bodies[0]).toEqual(expect.objectContaining({ decision: "choose_incoming", occupied_id: 41 })));
});

test("同优先级可保留原指定", async () => {
  const row = { ...pending, id: 40, version: 3, usage_type: "self", owner_name: "B", lifecycle_status: "manual_review", action: "choose_manually", comparison: "equal", conflict: { id: 41, designation_type: "top_three", version: 5, priority: 20 } };
  const bodies: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return Response.json(row); }));
  mount([row]);
  await fireEvent.click(screen.getByRole("button", { name: "保留原指定" }));
  await fireEvent.click(await screen.findByRole("button", { name: "确认保留原指定" }));
  await waitFor(() => expect(bodies[0]).toEqual(expect.objectContaining({ decision: "keep_occupied", occupied_id: 41 })));
});
