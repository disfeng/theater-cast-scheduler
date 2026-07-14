import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("monthly plan page supports selectable generation and closed dates", async () => {
  let generateBody: any = null;
  let performancesList: any[] = [];
  const performanceQueries: string[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      if (path === "/auth/login") return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西幽剧场", default_weekly_template: {} }]), { status: 200 });
      
      if (path === "/admin/monthly-plan/generate" && method === "POST") {
        generateBody = body;
        performancesList = [
          { id: 10, theater_id: body.theater_id, performance_date: `${body.year}-07-01`, slot: "early", status: "draft" }
        ];
        return new Response(JSON.stringify(performancesList), { status: 200 });
      }
      
      if (path.startsWith("/admin/performances")) {
        performanceQueries.push(path);
        return new Response(JSON.stringify(performancesList), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  const app = await renderAdminRoute("/admin/monthly-plan");
  await screen.findByText("西幽剧场");

  // Select theater
  await fireEvent.update(screen.getByLabelText("选择剧场"), "1");
  // Set year & month
  await fireEvent.update(screen.getByLabelText("年份"), "2027");
  await fireEvent.update(screen.getByLabelText("月份"), "7");
  // Fill closed dates
  await fireEvent.update(screen.getByLabelText("闭店日期"), "2027-07-02, 2027-07-09");
  // Generate
  await fireEvent.click(screen.getByRole("button", { name: "生成月度计划" }));

  await waitFor(() => {
    expect(generateBody).toEqual({
      theater_id: 1,
      year: 2027,
      month: 7,
      closed_dates: ["2027-07-02", "2027-07-09"],
    });
  });

  expect(await screen.findByText("2027-07-01")).toBeInTheDocument();
  expect(await screen.findByText("下午场")).toBeInTheDocument();
  expect(performanceQueries).toContain(
    "/admin/performances?theater_id=1&year=2027&month=7",
  );
});

test("monthly plan page displays generation conflicts", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/theaters") {
        return new Response(
          JSON.stringify([{ id: 1, name: "西幽剧场", default_weekly_template: {} }]),
          { status: 200 }
        );
      }
      if (path.startsWith("/admin/performances")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === "/admin/monthly-plan/generate" && init?.method === "POST") {
        return new Response(
          JSON.stringify({ detail: "monthly_plan_has_non_draft_performances" }),
          { status: 409 }
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  const app = await renderAdminRoute("/admin/monthly-plan");
  await screen.findByText("西幽剧场");
  await fireEvent.click(screen.getByRole("button", { name: "生成月度计划" }));

  expect(
    await screen.findByText("monthly_plan_has_non_draft_performances")
  ).toHaveAttribute("role", "alert");
});

test("monthly plan page supports adding and deleting custom performances", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      requests.push({ method, path, body });

      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/theaters") {
        return new Response(JSON.stringify([{ id: 1, name: "西幽剧场", default_weekly_template: {} }]), { status: 200 });
      }
      if (path.startsWith("/admin/performances")) {
        if (method === "GET") {
          const hasCreated = requests.some(r => r.method === "POST" && r.path === "/admin/performances");
          const hasDeleted = requests.some(r => r.method === "DELETE" && r.path.startsWith("/admin/performances/"));
          if (hasCreated && !hasDeleted) {
            return new Response(JSON.stringify([{ id: 99, theater_id: 1, performance_date: "2026-06-15", slot: "early", status: "draft" }]), { status: 200 });
          }
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (method === "POST") {
          return new Response(JSON.stringify({ id: 99, theater_id: 1, performance_date: "2026-06-15", slot: "early", status: "draft" }), { status: 200 });
        }
        if (method === "DELETE") {
          return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
        }
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  const app = await renderAdminRoute("/admin/monthly-plan");
  await screen.findByText("西幽剧场");

  // Fill in manual performance creation form
  await fireEvent.update(screen.getByLabelText("选择日期"), "2026-06-15");
  await fireEvent.update(screen.getByLabelText("场次选择"), "early");
  await fireEvent.click(screen.getByRole("button", { name: "确认添加" }));

  // Verify added
  await screen.findByText("自定义场次添加成功！");
  await screen.findByText("2026-06-15");

  // Verify list request was sent
  expect(requests.some(r => r.method === "POST" && r.path === "/admin/performances")).toBe(true);

  // Mock window.confirm
  vi.spyOn(window, "confirm").mockImplementation(() => true);

  // Delete performance
  await fireEvent.click(screen.getByRole("button", { name: "删除场次" }));

  // Verify deleted message
  await screen.findByText("场次删除成功！");
  expect(requests.some(r => r.method === "DELETE" && r.path === "/admin/performances/99")).toBe(true);
});
