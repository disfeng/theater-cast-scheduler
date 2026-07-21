import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderActorRoute, renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("actor schedule view", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/actor/me/calendar?")) {
        return new Response(
          JSON.stringify({ month: "2026-07", performances: [
            { notification_id: 1, theater_id: 1, theater_name: "西安幽州剧场", performance_id: 1,
              performance_date: "2026-06-15", slot_name: "下午场", start_time: "16:00:00",
              role_name: "长离", player_name: "Jennifer", designation_type: "universal",
              designation_label: "万能指定", read_at: null }
          ]}),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderActorRoute("/actor/schedule");
  
  await screen.findByRole("heading", { name: "我的排班" });
  expect(await screen.findByText("6月15日")).toBeInTheDocument();
  expect(await screen.findByText(/下午场/)).toBeInTheDocument();
  expect(await screen.findByText("长离")).toBeInTheDocument();
  expect(await screen.findByText("万能指定")).toBeInTheDocument();
});

test("actor submit leave request", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      requests.push({ method, path, body });

      if (path === "/actor/me/profile") {
        return new Response(JSON.stringify({ id: 1, display_name: "小A", phone_number: "13800000000", must_change_password: false, theaters: [{ id: 2, name: "西安幽州剧场", is_entry_theater: true }] }), { status: 200 });
      }
      if (path === "/actor/me/leave-applications") {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderActorRoute("/actor/leave");

  await screen.findByRole("heading", { name: "请假申请" });
  expect((await screen.findAllByText("西安幽州剧场")).length).toBeGreaterThan(0);
  expect(screen.getByText("按剧场选择一个或多个日期，每个日期可独立审批。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "提交请假" })).toBeDisabled();
  expect(requests.some(row => row.path === "/actor/me/leave-applications")).toBe(true);
});

test("admin review leave requests", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  let leaveList = [
    { id: 9, actor_id: 1, actor_name: "小展", theater_id: 2, theater_name: "西安幽州剧场", note: "生病", created_at: "2026-06-12T10:00:00", days: [
      { id: 45, leave_date: "2026-06-16", status: "pending", has_schedule_conflict: true, review_reason: null, reviewed_at: null, withdrawn_at: null }
    ] }
  ];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      requests.push({ method, path, body });

      if (path === "/admin/theaters") {
        return new Response(JSON.stringify([{ id: 2, name: "西安幽州剧场", status: "active" }]), { status: 200 });
      }
      if (path.startsWith("/admin/leave-applications")) {
        return new Response(JSON.stringify(leaveList), { status: 200 });
      }
      if (path === "/admin/leave-application-days/45/review" && method === "POST") {
        leaveList[0].days[0].status = body.status;
        return new Response(JSON.stringify(leaveList[0].days[0]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderAdminRoute("/admin/leave-requests");

  await screen.findByRole("heading", { name: "请假审核" });
  expect((await screen.findAllByText("小展")).length).toBeGreaterThan(0);
  await screen.findByText("6月16日");
  await screen.findByText("需调整排班");
  await waitFor(() => {
    expect(requests.some(row => row.method === "GET" && row.path === "/admin/leave-applications?theater_id=2")).toBe(true);
  });
  expect(document.querySelector(".request-list")).toBeInTheDocument();
  expect(document.querySelector(".date-actions-grid")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("搜索演员或备注")).toBeInTheDocument();
  expect(screen.getByText("筛选演员")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("开始日期")).toBeInTheDocument();

  await fireEvent.click(screen.getByRole("button", { name: "批准6月16日" }));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/leave-application-days/45/review",
      body: { status: "approved", reason: null }
    });
  });

  expect((await screen.findAllByText("已批准")).length).toBeGreaterThan(0);
});
