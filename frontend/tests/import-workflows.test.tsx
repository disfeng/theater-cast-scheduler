import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { expect, test, vi } from "vitest";
import App from "../src/App";

test("designation and wish import parse and resume workflow", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  const requestedPaths: string[] = [];
  
  const mockTheaters = [{ id: 1, name: "西幽剧场", default_weekly_template: {} }];
  const mockActors = [
    { id: 10, display_name: "小展", max_consecutive_performances: 3, rating_level: "normal", low_rating_monthly_cap: null, notes: null, role_ids: [100] }
  ];
  const mockRoles = [{ id: 100, name: "长离", group_name: "女位" }];
  const mockPerformances = [
    { id: 200, theater_id: 1, performance_date: "2026-06-01", slot: "early", status: "draft" }
  ];

  let draftData: any = {
    id: 5,
    weekly_batch_id: 2,
    raw_text: "#指定信息\n【虔诚许愿】-小展/长离-Jennifer",
    status: "draft",
    items: [
      {
        id: 50,
        import_draft_id: 5,
        item_kind: "wish",
        raw_line: "【虔诚许愿】-小展/长离-Jennifer",
        designation_type: null,
        player_name: "Jennifer",
        actor_name_raw: "小展",
        role_name_raw: "长离",
        actor_id: 10,
        role_id: 100,
        target_performance_id: null,
        note: null,
        validation_status: "valid",
        failure_reason: null,
        confirmed_at: null,
        designation_id: null,
        wish_id: null
      }
    ]
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.replace("http://localhost:8000", "");
      requestedPaths.push(path);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      if (method === "POST" || method === "PUT" || method === "PATCH") {
        requests.push({ method, path, body });
      }

      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/theaters") {
        return new Response(JSON.stringify(mockTheaters), { status: 200 });
      }
      if (path === "/admin/actors") {
        return new Response(JSON.stringify(mockActors), { status: 200 });
      }
      if (path === "/admin/roles") {
        return new Response(JSON.stringify(mockRoles), { status: 200 });
      }
      if (path.startsWith("/admin/performances")) {
        return new Response(JSON.stringify(mockPerformances), { status: 200 });
      }
      if (path === "/admin/weekly-batches") {
        if (method === "POST") {
          return new Response(JSON.stringify({ id: 2, theater_id: body.theater_id, week_start: body.week_start, status: "draft", created_at: "2026-06-01" }), { status: 200 });
        }
      }
      if (path.startsWith("/admin/import-drafts/parse")) {
        return new Response(JSON.stringify(draftData), { status: 200 });
      }
      if (path.startsWith("/admin/import-drafts/5")) {
        return new Response(JSON.stringify(draftData), { status: 200 });
      }
      if (path.startsWith("/admin/import-drafts")) {
        return new Response(JSON.stringify([draftData]), { status: 200 });
      }
      if (path.startsWith("/admin/import-draft-items/50/confirm")) {
        draftData.items[0].confirmed_at = "2026-06-01";
        draftData.items[0].wish_id = 99;
        draftData.status = "confirmed";
        return new Response(JSON.stringify(draftData.items[0]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );

  // 1. Render App and login
  const { unmount } = render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("指定与许愿")).toBeInTheDocument());
  fireEvent.click(screen.getByText("指定与许愿"));

  // 2. Select batch info
  await screen.findByText("西幽剧场");
  fireEvent.change(screen.getByLabelText("选择剧场"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("周一日期"), { target: { value: "2026-06-29" } });
  fireEvent.click(screen.getByText("创建/打开批次"));

  await waitFor(() => {
    expect(requestedPaths.some((path) => path.includes("year=2026&month=6"))).toBe(true);
    expect(requestedPaths.some((path) => path.includes("year=2026&month=7"))).toBe(true);
  });

  // 3. Paste and parse text
  await screen.findByText("导入统计文本");
  fireEvent.change(screen.getByLabelText("群统计文本"), { target: { value: "#指定信息\n【虔诚许愿】-小展/长离-Jennifer" } });
  fireEvent.click(screen.getByText("解析"));

  // 4. Verify draft row and confirmation
  await screen.findByDisplayValue("Jennifer");
  expect(screen.getByText("小展")).toBeInTheDocument();
  expect(screen.getByText("长离")).toBeInTheDocument();

  // Click confirm
  fireEvent.click(screen.getByText("确认"));
  await waitFor(() => expect(screen.getByText("已确认")).toBeInTheDocument());

  // 5. Unmount and resume (reload page)
  unmount();
  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("指定与许愿")).toBeInTheDocument());
  fireEvent.click(screen.getByText("指定与许愿"));

  // Select batch info again
  await screen.findByText("西幽剧场");
  fireEvent.change(screen.getByLabelText("选择剧场"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("周一日期"), { target: { value: "2026-06-29" } });
  fireEvent.click(screen.getByText("创建/打开批次"));

  // Verify it is restored directly from server (already confirmed status)
  await screen.findByDisplayValue("Jennifer");
  expect(screen.getByText("已确认")).toBeInTheDocument();
});
