import { cleanup, fireEvent, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";
import { readFileSync } from "node:fs";

test("offers per-day publish with publication state and republish confirmation", () => {
  const source = readFileSync(`${process.cwd()}/src/pages/admin/WeeklySchedulingPage.vue`, "utf8");
  const api = readFileSync(`${process.cwd()}/src/api/admin.ts`, "utf8");
  expect(source).toContain('class="date-cell-content"');
  expect(source).toContain("day-action--publish");
  expect(source).toContain("day-action--changed");
  expect(source).toContain("day-status--published");
  expect(source).toContain("重新发布");
  expect(source).toContain("confirm_republish");
  expect(api).toContain("/admin/weekly-schedules/publish-day");
});

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

async function chooseActor(comboboxName: string, actorName = "小展") {
  const combobox = await screen.findByRole("combobox", { name: comboboxName });
  await fireEvent.click(combobox);
  const option = await screen.findByText(new RegExp(`^${actorName} · 本周\\d+$`), {
    selector: ".assignment-cell .el-select-dropdown__item span",
  });
  await fireEvent.click(option);
  return combobox;
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

test("uses compact Element Plus actor selectors in assignment cells", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return Response.json([{ id: 1, name: "西安幽州剧场", is_active: true }]);
    if (path.startsWith("/admin/weekly-schedules/workspace")) return Response.json(requestedWorkspace(input));
    return Response.json([]);
  }));

  const { container } = await renderAdminRoute("/admin/weekly-scheduling");
  await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" });

  expect(container.querySelector(".assignment-cell .assignment-select.el-select")).toBeInTheDocument();
  expect(container.querySelector(".assignment-cell > select")).not.toBeInTheDocument();
  expect(container.querySelector(".schedule-matrix")).toHaveClass("schedule-matrix--compact");
});

test("renders a predesignation as a locked cell with a detail link", async () => {
  const scrollIntoView = vi.fn(); Element.prototype.scrollIntoView = scrollIntoView;
  const locked = {
    ...workspace,
    assignments: [{ performance_id: 10, role_id: 20, actor_id: 30, source: "recommended", locked: true,
      designation_id: 77, designation_type: "universal", owner_player_name: "玩家A", beneficiary_player_name: "玩家B", entitlement_serial: "UNI-77" }],
    empty_slots: [],
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (url.pathname === "/admin/weekly-schedules/workspace") {
      return new Response(JSON.stringify(url.searchParams.get("week_start") === "2026-12-28" ? locked : monthWorkspace(url.searchParams.get("week_start")!)), { status: 200 });
    }
    if (["/admin/actors", "/admin/roles"].includes(url.pathname)) return new Response(JSON.stringify([]), { status: 200 });
    if (url.pathname === "/admin/designations") return Response.json([{
      id: 77, version: 1, usage_type: "self", lifecycle_status: "predesignated", verification_status: "not_required",
      designation_type: "universal", beneficiary_name: "玩家B", owner_name: "玩家A", performance_label: "2027-01-01 晚场",
      actor_name: "小展", role_name: "柳知雨", available_items: [], status_history: [], action: "none", conflict: null,
    }]);
    return new Response(JSON.stringify([]), { status: 200 });
  }));
  const app = await renderAdminRoute("/admin/weekly-scheduling");
  const select = await screen.findByRole("combobox", { name: "1月1日 晚场 柳知雨" });
  expect(select).toBeDisabled();
  const detail = screen.getByRole("button", { name: "查看指定 77 详情" });
  expect(detail).toHaveTextContent("预指定锁定 · 万能道具");
  expect(detail).toHaveTextContent("持有人 玩家A"); expect(detail).toHaveTextContent("使用玩家 玩家B"); expect(detail).toHaveTextContent("UNI-77");
  await fireEvent.click(screen.getByRole("button", { name: "查看指定 77 详情" }));
  await waitFor(() => expect(app.router.currentRoute.value.query).toMatchObject({ performance_id: "10", review_tab: "designations", designation_id: "77" }));
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
  await waitFor(() => expect(screen.getByRole("combobox", { name: "1月1日 晚场 柳知雨" }).closest(".assignment-cell")).toHaveTextContent("小展 · 本周1"));
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

  const select = await chooseActor("1月1日 晚场 柳知雨");
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

  const select = await chooseActor("1月1日 晚场 柳知雨");
  expect(select.closest(".assignment-cell")).toHaveTextContent("小展 · 本周1");

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

test("unmet confirmation shows exact refund and submits the server token and operation key", async () => {
  const bodies: any[]=[];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url=new URL(String(input));
    if(url.pathname==="/admin/theaters")return Response.json([{id:1,name:"西安幽州剧场",is_active:true}]);
    if(url.pathname==="/admin/weekly-schedules/workspace")return Response.json(requestedWorkspace(input));
    if(url.pathname==="/admin/weekly-schedules/publish"){
      const body=JSON.parse(String(init?.body));bodies.push(body);
      if(!body.confirmation_token)return Response.json({detail:{code:"unmet_designations_require_confirmation",
        confirmation_token:"confirm-token",idempotency_key:"publish-operation",
        designations:[{id:77,player_name:"使用玩家B",failure_reason:"actor_on_leave",entitlement_serial:"UNI-77",
          refund_target:"持有人A",refund_status:"expired"}]}},{status:409});
      return Response.json({...workspace,status:"scheduled",version:1});
    }
    return Response.json({conflicts:[],warnings:[],empty_slots:[]});
  }));
  await renderAdminRoute("/admin/weekly-scheduling");await screen.findByText("柳知雨");
  await fireEvent.click(screen.getByRole("button",{name:"发布 12月28日–1月3日"}));
  expect(await screen.findByText(/#77 使用玩家B：actor_on_leave/)).toBeInTheDocument();
  expect(screen.getByText(/UNI-77退回 持有人A（已过期）/)).toBeInTheDocument();
  await fireEvent.click(await screen.findByRole("button",{name:"确认发布并退回"}));
  await waitFor(()=>expect(bodies).toHaveLength(2));
  expect(bodies[1]).toEqual(expect.objectContaining({confirmation_token:"confirm-token",idempotency_key:"publish-operation"}));
});

test("cancelling unmet confirmation does not retry or cache its token", async () => {
  const bodies: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return Response.json([{ id: 1, name: "西安幽州剧场", is_active: true }]);
    if (url.pathname === "/admin/weekly-schedules/workspace") return Response.json(requestedWorkspace(input));
    if (url.pathname === "/admin/weekly-schedules/publish") {
      const body = JSON.parse(String(init?.body)); bodies.push(body);
      return Response.json({ detail: { code: "unmet_designations_require_confirmation",
        confirmation_token: "cancelled-token", idempotency_key: "cancelled-operation",
        designations: [{ id: 77, player_name: "玩家B", failure_reason: "actor_on_leave" }] } }, { status: 409 });
    }
    return Response.json({ conflicts: [], warnings: [], empty_slots: [] });
  }));
  await renderAdminRoute("/admin/weekly-scheduling"); await screen.findByText("柳知雨");
  const publish = screen.getByRole("button", { name: "发布 12月28日–1月3日" });
  await fireEvent.click(publish);
  await screen.findByRole("button", { name: "确认发布并退回" });
  await fireEvent.click(screen.getByRole("button", { name: "取消" }));
  await waitFor(() => expect(publish).not.toBeDisabled());
  expect(bodies).toHaveLength(1);
  expect(bodies.filter(body => body.confirmation_token)).toHaveLength(0);

  await fireEvent.click(publish);
  await waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies[1].confirmation_token).toBeUndefined();
  expect(bodies[1].idempotency_key).not.toBe("cancelled-operation");
  await screen.findByRole("button", { name: "确认发布并退回" });
  const cancelButtons = screen.getAllByRole("button", { name: "取消" });
  await fireEvent.click(cancelButtons[cancelButtons.length - 1]);
  await waitFor(() => expect(publish).not.toBeDisabled());
});

test("stale confirmation clears the old token before the next publish", async () => {
  const bodies: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === "/admin/theaters") return Response.json([{ id: 1, name: "西安幽州剧场", is_active: true }]);
    if (url.pathname === "/admin/weekly-schedules/workspace") return Response.json(requestedWorkspace(input));
    if (url.pathname === "/admin/weekly-schedules/publish") {
      const body = JSON.parse(String(init?.body)); bodies.push(body);
      if (body.confirmation_token) return Response.json({ detail: { code: "stale_confirmation" } }, { status: 409 });
      const suffix = bodies.length === 1 ? "old" : "new";
      return Response.json({ detail: { code: "unmet_designations_require_confirmation",
        confirmation_token: `${suffix}-token`, idempotency_key: `${suffix}-operation`,
        designations: [{ id: 77, player_name: "玩家B", failure_reason: "actor_on_leave" }] } }, { status: 409 });
    }
    return Response.json({ conflicts: [], warnings: [], empty_slots: [] });
  }));
  await renderAdminRoute("/admin/weekly-scheduling"); await screen.findByText("柳知雨");
  const publish = screen.getByRole("button", { name: "发布 12月28日–1月3日" });
  await fireEvent.click(publish);
  await fireEvent.click(await screen.findByRole("button", { name: "确认发布并退回" }));
  await waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies[1]).toEqual(expect.objectContaining({ confirmation_token: "old-token", idempotency_key: "old-operation" }));
  expect(await screen.findByText("指定或退款范围已变更，请重新发布并确认。")).toBeInTheDocument();
  await waitFor(() => expect(publish).not.toBeDisabled());

  await fireEvent.click(publish);
  await waitFor(() => expect(bodies).toHaveLength(3));
  expect(bodies[2].confirmation_token).toBeUndefined();
  expect(bodies[2].idempotency_key).not.toBe("old-operation");
  await screen.findByRole("button", { name: "确认发布并退回" });
  const cancelButtons = screen.getAllByRole("button", { name: "取消" });
  await fireEvent.click(cancelButtons[cancelButtons.length - 1]);
  await waitFor(() => expect(publish).not.toBeDisabled());
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

  await chooseActor("8月3日 早场 柳知雨");
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
  await chooseActor("8月3日 早场 柳知雨");

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
  await chooseActor("8月3日 早场 柳知雨");

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
  await chooseActor("8月3日 早场 柳知雨");

  await fireEvent.click(screen.getByRole("button", { name: "保存草稿（1 周）" }));
  expect(await screen.findByRole("button", { name: "确认保存" })).toBeInTheDocument();
  expect(await screen.findByText("超过演员个人最大连场数")).toBeInTheDocument();

  await fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
  await waitFor(() => expect(draftAttempts).toBe(2));
  const retryBody = JSON.parse(String(fetchMock.mock.calls.filter(([input]) => String(input).includes("/draft"))[1][1]?.body));
  expect(retryBody.confirm_conflicts).toBe(true);
});
