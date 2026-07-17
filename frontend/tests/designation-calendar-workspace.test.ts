import { fireEvent, screen, waitFor } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";

import { renderAdminRoute } from "./helpers/render-app";

const totals = { players: 1, designations: 1, wishes: 1, pending: 2, conflicts: 1 };

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") {
      return Response.json([{ id: 2, name: "西安幽州剧场", is_active: true }]);
    }
    if (path === "/admin/designation-workspace/month?theater_id=2&year=2026&month=8") {
      return Response.json({
        theater_id: 2,
        year: 2026,
        month: 8,
        totals,
        days: [{
          date: "2026-08-01",
          performances: [{
            id: 62,
            performance_date: "2026-08-01",
            slot_name: "晚场",
            start_time: "19:30:00",
            status: "planned",
            totals,
          }],
        }],
      });
    }
    if (path === "/admin/designation-workspace/performances/62") {
      return Response.json({
        performance: { id: 62, theater_id: 2, theater_name: "西安幽州剧场", performance_date: "2026-08-01", slot_name: "晚场", start_time: "19:30:00", status: "planned", totals },
        players: [{ id: 8, player_id: 7, player_name: "Jennifer", theater_visit_count: 14, role_visit_count: 3, role_name: "长离", status: "active" }],
        designations: [{ id: 9, version: 1, usage_type: "self", beneficiary_name: "Jennifer", actor_name: "小展", role_name: "长离", lifecycle_status: "draft", verification_status: "verified", designation_type: "universal", priority: 30, owner_name: "Jennifer", owner_player_id: 7, entitlement_item_id: null, available_items: [{ id: 18, serial_number: "UNI-018", source_label: "6 月热力榜", expires_at: "2026-09-30", status: "available" }], conflict: null, action: "activate", status_history: [] }],
        wishes: [{ id: 11, version: 1, player_name: "Jennifer", actor_name: "小展", role_name: "长离", status: "active" }],
        conflicts: [{ code: "MAX_CONSECUTIVE_REACHED", severity: "warning", message: "已达到最大连场", designation_id: 9 }],
      });
    }
    if (path === "/admin/performances/62/board") {
      return Response.json({ id: 4, performance_id: 62, current_revision_id: null, revisions: [] });
    }
    if (path === "/admin/actors" || path === "/admin/roles") return Response.json([]);
    if (path === "/admin/designations/9/cancel" && init?.method === "POST") {
      return Response.json({ id: 9, version: 2, lifecycle_status: "cancelled" });
    }
    if (path === "/admin/designations/9/activate" && init?.method === "POST") {
      return Response.json({ id: 9, version: 2, lifecycle_status: "predesignated" });
    }
    return Response.json({ detail: `unexpected:${path}` }, { status: 500 });
  }));
});

test("按剧场月份展示统一日历并按需打开场次审核抽屉", async () => {
  const mounted = await renderAdminRoute("/admin/designations-wishes?theater_id=2&year=2026&month=8");

  expect(screen.queryByRole("tab", { name: "导入微信群信息" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "场次信息板" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "预指定核对" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "月度工作台" })).not.toBeInTheDocument();
  expect(await screen.findByText("2026 年 8 月")).toBeInTheDocument();
  expect(await screen.findAllByTestId("calendar-weekday")).toHaveLength(7);
  expect(screen.getAllByText("1 位玩家")).toHaveLength(2);
  expect(screen.getAllByText("1 条指定")).toHaveLength(2);
  expect(screen.getAllByText("1 条许愿")).toHaveLength(2);

  await fireEvent.click(screen.getByRole("button", { name: /8月1日 晚场/ }));
  expect(await screen.findByRole("heading", { name: "8月1日 · 晚场" })).toBeInTheDocument();
  expect(screen.getAllByText("Jennifer")).toHaveLength(4);
  expect(screen.getByText("14 刷剧场 · 3 刷角色")).toBeInTheDocument();
  expect(screen.getByText("已达到最大连场")).toBeInTheDocument();
  await waitFor(() => expect(mounted.router.currentRoute.value.query.performance_id).toBe("62"));
});

test("场次抽屉可填写理由拒绝指定", async () => {
  await renderAdminRoute("/admin/designations-wishes?theater_id=2&year=2026&month=8");
  await fireEvent.click(await screen.findByRole("button", { name: /8月1日 晚场/ }));
  await fireEvent.click(await screen.findByRole("tab", { name: "指定 (1)" }));
  await fireEvent.click(screen.getByRole("button", { name: "拒绝指定 Jennifer" }));
  await fireEvent.update(screen.getByLabelText("拒绝原因"), "演员已超过最大连场");
  await fireEvent.click(screen.getByRole("button", { name: "确认拒绝" }));

  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([input, init]) => {
    if (!String(input).endsWith("/admin/designations/9/cancel") || init?.method !== "POST") return false;
    return JSON.parse(String(init.body)).reason === "演员已超过最大连场";
  })).toBe(true));
});

test("场次抽屉内可直接管理该场信息板", async () => {
  const mounted = await renderAdminRoute("/admin/designations-wishes?theater_id=2&year=2026&month=8");
  await fireEvent.click(await screen.findByRole("button", { name: /8月1日 晚场/ }));
  await fireEvent.click(await screen.findByRole("tab", { name: "场次信息板" }));

  expect(await screen.findByText("该场次尚无信息板版本")).toBeInTheDocument();
  expect(screen.getByLabelText("信息板原文")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).endsWith("/admin/performances/62/board"))).toBe(true);
  await waitFor(() => expect(mounted.router.currentRoute.value.query.review_tab).toBe("board"));
});

test("场次抽屉内可选择具体权益并激活本场指定", async () => {
  await renderAdminRoute("/admin/designations-wishes?theater_id=2&year=2026&month=8");
  await fireEvent.click(await screen.findByRole("button", { name: /8月1日 晚场/ }));
  await fireEvent.click(await screen.findByRole("tab", { name: "指定 (1)" }));

  expect(screen.getAllByText("UNI-018 · 6 月热力榜").length).toBeGreaterThan(0);
  await fireEvent.click(screen.getByRole("button", { name: "核验并预占" }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/admin/designations/9/activate") && init?.method === "POST")).toBe(true));
});

test("刷新带场次参数的链接会直接恢复审核抽屉", async () => {
  await renderAdminRoute("/admin/designations-wishes?theater_id=2&year=2026&month=8&performance_id=62&review_tab=wishes");
  expect(await screen.findByRole("heading", { name: "8月1日 · 晚场" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "许愿 (1)" })).toHaveAttribute("aria-selected", "true");
});
