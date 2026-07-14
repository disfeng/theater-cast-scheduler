import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderActorRoute, renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("actor schedule view", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/actor/me/schedule")) {
        return new Response(
          JSON.stringify([
            { date: "2026-06-15", slot: "early", role: "长离", status: "published" }
          ]),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderActorRoute("/actor/schedule");
  
  await screen.findByRole("heading", { name: "我的排班" });
  expect(await screen.findByText("2026-06-15")).toBeInTheDocument();
  expect(await screen.findByText("下午场")).toBeInTheDocument();
  expect(await screen.findByText("长离")).toBeInTheDocument();
  expect(await screen.findByText("已发布")).toBeInTheDocument();
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

      if (path === "/actor/me/leave-requests" && method === "POST") {
        return new Response(JSON.stringify({ status: "submitted", dates: ["2026-06-16", "2026-06-17"] }), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderActorRoute("/actor/leave");

  await screen.findByRole("heading", { name: "我的请假" });
  await fireEvent.update(screen.getByLabelText("请假日期"), "2026-06-16, 2026-06-17");
  await fireEvent.update(screen.getByLabelText("备注"), "休息一下");
  await fireEvent.click(screen.getByRole("button", { name: "提交请假" }));

  await screen.findByText("请假申请提交成功！");
  expect(requests).toContainEqual({
    method: "POST",
    path: "/actor/me/leave-requests",
    body: { dates: ["2026-06-16", "2026-06-17"], note: "休息一下" }
  });
});

test("admin review leave requests", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  let leaveList = [
    { id: 45, actor_name: "小展", leave_date: "2026-06-16", status: "pending", note: "生病" }
  ];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      requests.push({ method, path, body });

      if (path === "/admin/leave-requests") {
        return new Response(JSON.stringify(leaveList), { status: 200 });
      }
      if (path === "/admin/leave-requests/45/review" && method === "POST") {
        leaveList[0].status = body.status;
        return new Response(JSON.stringify(leaveList[0]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  await renderAdminRoute("/admin/leave-requests");

  await screen.findByRole("heading", { name: "请假审核" });
  await screen.findByText("小展");
  await screen.findByText("2026-06-16");
  await screen.findByText("pending");

  await fireEvent.click(screen.getByRole("button", { name: "批准" }));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/leave-requests/45/review",
      body: { status: "approved" }
    });
  });

  await screen.findByText("approved");
});
