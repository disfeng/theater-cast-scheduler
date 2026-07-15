import { cleanup, fireEvent, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";

const workspace = {
  theater_id: 1, week_start: "2026-12-28", week_end: "2027-01-03", batch_id: null,
  status: "uncreated", version: 0, updated_at: null, published_at: null,
  performances: [{ id: 10, performance_date: "2027-01-01", slot_name: "晚场", start_time: "19:30:00", sort_order: 1 }],
  roles: [{ id: 20, name: "柳知雨", group_name: "女" }],
  actors: [{ id: 30, display_name: "小展", rating_level: "normal", max_consecutive_performances: 3, low_rating_monthly_cap: null, role_ids: [20], weekly_count: 0, monthly_count: 0 }],
  assignments: [], conflicts: [], conflict_summary: {}, warnings: [], warning_summary: {}, empty_slots: [{ performance_id: 10, role_id: 20 }],
  unsatisfied_designations: [], unsatisfied_wishes: [],
};

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 11, 30));
});
afterEach(() => cleanup());

test("loads a theater week and exposes the role assignment matrix", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  }));
  const app = await renderAdminRoute("/admin/weekly-scheduling");

  expect(await screen.findByRole("heading", { name: "周排班" })).toBeInTheDocument();
  expect(await screen.findByText("2026/12/28 - 2027/01/03")).toBeInTheDocument();
  expect(screen.getByText("柳知雨")).toBeInTheDocument();
  expect(screen.getByText("1月1日")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "1月1日 晚场 柳知雨" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "推荐排班" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发布排班" })).toBeInTheDocument();
  expect(app.router.currentRoute.value.fullPath).toBe("/admin/weekly-scheduling");
});

test("preserves manual cells when applying recommendations", async () => {
  const recommended = { ...workspace, assignments: [
    { performance_id: 10, role_id: 20, actor_id: 30, source: "recommended", conflict_codes: [] },
  ], empty_slots: [] };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    if (path === "/admin/weekly-schedules/recommend") return new Response(JSON.stringify(recommended), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByText("柳知雨");
  await fireEvent.click(screen.getByRole("button", { name: "推荐排班" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "1月1日 晚场 柳知雨" })).toHaveValue("30"));
});

test("automatically validates conflicts after an actor selection", async () => {
  const conflict = {
    code: "actor_on_leave", message: "演员当天已批准请假",
    performance_id: 10, role_id: 20, actor_id: 30,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    if (path === "/admin/weekly-schedules/validate") return new Response(JSON.stringify({ conflicts: [conflict], empty_slots: [] }), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");

  const select = await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" });
  await fireEvent.update(select, "30");
  await vi.advanceTimersByTimeAsync(300);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:7004/admin/weekly-schedules/validate",
    expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByText("1 个冲突")).toBeInTheDocument();
  expect(select.closest(".assignment-cell")).toHaveClass("has-conflict");
});

test("updates weekly counts immediately and renders reached limits as warnings", async () => {
  const warning = {
    code: "consecutive_limit_reached", message: "已达到演员个人最大连场数",
    performance_id: 10, role_id: 20, actor_id: 30,
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    if (path === "/admin/weekly-schedules/validate") return new Response(JSON.stringify({ conflicts: [], warnings: [warning], empty_slots: [] }), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  }));
  await renderAdminRoute("/admin/weekly-scheduling");

  const select = await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" });
  await fireEvent.update(select, "30");
  expect(screen.getByRole("option", { name: "小展 · 本周1" })).toBeInTheDocument();

  await vi.advanceTimersByTimeAsync(300);
  expect(await screen.findByText("1 个提醒")).toBeInTheDocument();
  expect(select.closest(".assignment-cell")).toHaveClass("has-warning");
});

test("shows a blocking dialog when publishing a partially assigned performance", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(workspace), { status: 200 });
    if (path === "/admin/weekly-schedules/publish") return new Response(JSON.stringify({
      detail: { code: "incomplete_performances", performances: [{ performance_id: 10, missing_role_ids: [21] }] },
    }), { status: 409 });
    return new Response(JSON.stringify({}), { status: 200 });
  }));
  await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByText("柳知雨");

  await fireEvent.click(screen.getByRole("button", { name: "发布排班" }));

  expect(await screen.findByText("无法发布排班")).toBeInTheDocument();
  expect(screen.getByText("存在未完成角色安排的演出场次，请补充完整后再发布。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "返回补充" })).toBeInTheDocument();
  expect(screen.queryByText("有演出场次尚未完成全部角色安排，无法发布")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "确认发布" })).not.toBeInTheDocument();
});
