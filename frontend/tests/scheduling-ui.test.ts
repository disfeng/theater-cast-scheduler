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

function monthWorkspace(weekStart: string, performances: typeof workspace.performances = []) {
  const end = new Date(`${weekStart}T00:00:00`);
  end.setDate(end.getDate() + 6);
  return {
    ...workspace,
    week_start: weekStart,
    week_end: end.toISOString().slice(0, 10),
    performances,
    empty_slots: performances.map((performance) => ({ performance_id: performance.id, role_id: 20 })),
  };
}

function requestedWorkspace(input: RequestInfo | URL) {
  const url = new URL(String(input));
  const weekStart = url.searchParams.get("week_start")!;
  return monthWorkspace(weekStart, weekStart === "2026-12-28" ? workspace.performances : []);
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 11, 30));
});
afterEach(() => cleanup());

test("loads a theater week and exposes the role assignment matrix", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const app = await renderAdminRoute("/admin/weekly-scheduling");

  expect(await screen.findByRole("heading", { name: "周排班" })).toBeInTheDocument();
  expect(await screen.findByText("2026/12/28 - 2027/01/03")).toBeInTheDocument();
  expect(await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "推荐当前周" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发布 12月28日–1月3日" })).toBeInTheDocument();
  expect(app.router.currentRoute.value.fullPath).toBe("/admin/weekly-scheduling");
});

test("renders the compact two-row toolbar", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  }));
  const { container } = await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByRole("heading", { name: "周排班" });

  expect(container.querySelectorAll(".toolbar-primary")).toHaveLength(1);
  expect(container.querySelectorAll(".toolbar-secondary")).toHaveLength(1);
  expect(container.querySelector(".toolbar-summary")).toHaveTextContent("当前操作周");
  expect(container.querySelectorAll(".status-pill").length).toBeGreaterThanOrEqual(2);
});

test("moves to the next week across a month boundary", async () => {
  vi.setSystemTime(new Date(2026, 7, 31));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") return new Response(JSON.stringify(monthWorkspace(url.searchParams.get("week_start")!)), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  }));
  await renderAdminRoute("/admin/weekly-scheduling");
  expect(await screen.findByText("2026/08/31 - 2026/09/06")).toBeInTheDocument();
  expect(await screen.findByText("本周没有演出场次，请先生成月度计划")).toBeInTheDocument();

  await fireEvent.click(screen.getByRole("button", { name: "下一周" }));

  expect(await screen.findByText("2026 年 9 月")).toBeInTheDocument();
  expect(await screen.findByText("2026/09/07 - 2026/09/13")).toBeInTheDocument();
});

test("renders only the active natural week as a role matrix", async () => {
  vi.setSystemTime(new Date(2026, 7, 5));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      const weekStart = url.searchParams.get("week_start")!;
      const performances = weekStart === "2026-08-03"
        ? [{ id: 11, performance_date: "2026-08-05", slot_name: "下午场", start_time: "16:00:00", sort_order: 1 }]
        : weekStart === "2026-08-10"
          ? [{ id: 12, performance_date: "2026-08-12", slot_name: "晚场", start_time: "19:30:00", sort_order: 2 }]
          : [];
      return new Response(JSON.stringify(monthWorkspace(weekStart, performances)), { status: 200 });
    }
    return new Response(JSON.stringify({}), { status: 200 });
  }));
  const { container } = await renderAdminRoute("/admin/weekly-scheduling");

  await screen.findByText("2026 年 8 月");
  expect(await screen.findByRole("combobox", { name: "8月5日 下午场 柳知雨" })).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "8月12日 晚场 柳知雨" })).not.toBeInTheDocument();
  expect(container.querySelector(".schedule-matrix")).toBeInTheDocument();

  await fireEvent.click(screen.getByRole("button", { name: "下一周" }));

  expect(await screen.findByRole("combobox", { name: "8月12日 晚场 柳知雨" })).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "8月5日 下午场 柳知雨" })).not.toBeInTheDocument();
});

test("preserves manual cells when applying recommendations", async () => {
  const recommended = { ...workspace, assignments: [
    { performance_id: 10, role_id: 20, actor_id: 30, source: "recommended", conflict_codes: [] },
  ], empty_slots: [] };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    if (path === "/admin/weekly-schedules/recommend") return new Response(JSON.stringify(recommended), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByText("柳知雨");
  await fireEvent.click(screen.getByRole("button", { name: "推荐当前周" }));
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
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    if (path === "/admin/weekly-schedules/validate-context") return new Response(JSON.stringify({ conflicts: [conflict], warnings: [], empty_slots: [] }), { status: 200 });
    return new Response(JSON.stringify({}), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");

  const select = await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" });
  await fireEvent.update(select, "30");
  await vi.advanceTimersByTimeAsync(300);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:7004/admin/weekly-schedules/validate-context",
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
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    if (path === "/admin/weekly-schedules/validate-context") return new Response(JSON.stringify({ conflicts: [], warnings: [warning], empty_slots: [] }), { status: 200 });
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
    if (path.startsWith("/admin/weekly-schedules/workspace")) return new Response(JSON.stringify(requestedWorkspace(input)), { status: 200 });
    if (path === "/admin/weekly-schedules/publish") return new Response(JSON.stringify({
      detail: { code: "incomplete_performances", performances: [{ performance_id: 10, missing_role_ids: [21] }] },
    }), { status: 409 });
    return new Response(JSON.stringify({}), { status: 200 });
  }));
  await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByText("柳知雨");

  await fireEvent.click(screen.getByRole("button", { name: "发布 12月28日–1月3日" }));

  expect(await screen.findByText("无法发布排班")).toBeInTheDocument();
  expect(screen.getByText("存在未完成角色安排的演出场次，请补充完整后再发布。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "返回补充" })).toBeInTheDocument();
  expect(screen.queryByText("有演出场次尚未完成全部角色安排，无法发布")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "确认发布" })).not.toBeInTheDocument();
});

test("saves the dirty active natural week", async () => {
  vi.setSystemTime(new Date(2026, 7, 3));
  const monday = { id: 11, performance_date: "2026-08-03", slot_name: "早场", start_time: "12:30:00", sort_order: 0 };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      const start = url.searchParams.get("week_start")!;
      const performances = start === "2026-08-03" ? [monday] : [];
      return new Response(JSON.stringify(monthWorkspace(start, performances)), { status: 200 });
    }
    if (url.pathname === "/admin/weekly-schedules/draft") {
      const body = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ ...monthWorkspace(body.week_start, [monday]), assignments: body.assignments, version: 1, status: "ready" }), { status: 200 });
    }
    return new Response(JSON.stringify({ conflicts: [], warnings: [], empty_slots: [] }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");

  await fireEvent.update(await screen.findByRole("combobox", { name: "8月3日 早场 柳知雨" }), "30");
  await fireEvent.click(screen.getByRole("button", { name: "保存草稿（1 周）" }));

  await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/admin/weekly-schedules/draft"))).toHaveLength(1));
  const bodies = fetchMock.mock.calls
    .filter(([input]) => String(input).includes("/admin/weekly-schedules/draft"))
    .map(([, init]) => JSON.parse(String(init?.body)));
  expect(bodies.map((body) => body.week_start)).toEqual(["2026-08-03"]);
});

test("guards month navigation when local weeks are dirty", async () => {
  vi.setSystemTime(new Date(2026, 7, 3));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      const start = url.searchParams.get("week_start")!;
      const performances = start === "2026-08-03" ? [{ id: 11, performance_date: "2026-08-03", slot_name: "早场", start_time: "12:30:00", sort_order: 0 }] : [];
      return new Response(JSON.stringify(monthWorkspace(start, performances)), { status: 200 });
    }
    return new Response(JSON.stringify({ conflicts: [], warnings: [], empty_slots: [] }), { status: 200 });
  }));
  await renderAdminRoute("/admin/weekly-scheduling");
  await fireEvent.update(await screen.findByRole("combobox", { name: "8月3日 早场 柳知雨" }), "30");

  await fireEvent.click(screen.getByRole("button", { name: "下个月" }));

  expect(await screen.findByText("存在未保存的排班修改")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存后切换" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "放弃修改" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
  expect(screen.getByText("2026 年 8 月")).toBeInTheDocument();
});

test("guards theater changes when local weeks are dirty", async () => {
  vi.setSystemTime(new Date(2026, 7, 3));
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([
      { id: 1, name: "西安幽州剧场", is_active: true },
      { id: 2, name: "长安剧场", is_active: true },
    ]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      const start = url.searchParams.get("week_start")!;
      const performances = start === "2026-08-03" ? [{ id: 11, performance_date: "2026-08-03", slot_name: "早场", start_time: "12:30:00", sort_order: 0 }] : [];
      return new Response(JSON.stringify(monthWorkspace(start, performances)), { status: 200 });
    }
    return new Response(JSON.stringify({ conflicts: [], warnings: [], empty_slots: [] }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");
  await fireEvent.update(await screen.findByRole("combobox", { name: "8月3日 早场 柳知雨" }), "30");

  await fireEvent.click(screen.getByRole("combobox", { name: "剧场" }));
  await fireEvent.click(await screen.findByText("长安剧场"));

  expect(await screen.findByText("存在未保存的排班修改")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("theater_id=2"))).toBe(false);
});

test("asks for confirmation and retries a conflicting dirty week", async () => {
  vi.setSystemTime(new Date(2026, 7, 3));
  let draftAttempts = 0;
  const performance = { id: 11, performance_date: "2026-08-03", slot_name: "早场", start_time: "12:30:00", sort_order: 0 };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      const start = url.searchParams.get("week_start")!;
      return new Response(JSON.stringify(monthWorkspace(start, start === "2026-08-03" ? [performance] : [])), { status: 200 });
    }
    if (url.pathname === "/admin/weekly-schedules/draft") {
      draftAttempts += 1;
      const body = JSON.parse(String(init?.body));
      if (!body.confirm_conflicts) return new Response(JSON.stringify({ detail: {
        code: "conflicts_require_confirmation",
        conflicts: [{ code: "consecutive_limit_exceeded", message: "超过演员个人最大连场数", performance_id: 11, role_id: 20, actor_id: 30 }],
      } }), { status: 409 });
      return new Response(JSON.stringify({ ...monthWorkspace(body.week_start, [performance]), assignments: body.assignments, version: 1, status: "ready" }), { status: 200 });
    }
    return new Response(JSON.stringify({ conflicts: [], warnings: [], empty_slots: [] }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  await renderAdminRoute("/admin/weekly-scheduling");
  await fireEvent.update(await screen.findByRole("combobox", { name: "8月3日 早场 柳知雨" }), "30");

  await fireEvent.click(screen.getByRole("button", { name: "保存草稿（1 周）" }));
  expect(await screen.findByRole("button", { name: "确认保存" })).toBeInTheDocument();
  expect(await screen.findByText("超过演员个人最大连场数")).toBeInTheDocument();

  await fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
  await waitFor(() => expect(draftAttempts).toBe(2));
  const retryBody = JSON.parse(String(fetchMock.mock.calls.filter(([input]) => String(input).includes("/draft"))[1][1]?.body));
  expect(retryBody.confirm_conflicts).toBe(true);
});
