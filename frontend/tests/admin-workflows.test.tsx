import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { expect, test, vi } from "vitest";
import App from "../src/App";

test("admin shell exposes settings and actor management pages", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (url.endsWith("/admin/theaters")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/roles")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/actors")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("基础配置")).toBeInTheDocument());
  fireEvent.click(screen.getByText("基础配置"));
  expect(await screen.findByText("剧场配置")).toBeInTheDocument();
  fireEvent.click(screen.getByText("演员管理"));
  expect(await screen.findByText("新增演员")).toBeInTheDocument();
});

test("monthly plan page loads theaters and performances", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      if (url.endsWith("/admin/theaters")) return new Response(JSON.stringify([{ id: 1, name: "西幽剧场", default_weekly_template: {} }]), { status: 200 });
      if (url.includes("/admin/performances")) return new Response(JSON.stringify([{ id: 1, theater_id: 1, performance_date: "2026-06-01", slot: "early", status: "draft" }]), { status: 200 });
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("月度计划")).toBeInTheDocument());
  fireEvent.click(screen.getByText("月度计划"));
  expect(await screen.findByText("西幽剧场")).toBeInTheDocument();
  expect(await screen.findByText("2026-06-01 early")).toBeInTheDocument();
});

test("theater and role entry workflows", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  const theatersList: any[] = [];
  const rolesList: any[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.replace("http://localhost:8000", "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      if (method === "POST" || method === "PUT" || method === "PATCH") {
        requests.push({ method, path, body });
      }

      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/theaters") {
        if (method === "POST") {
          const newTheater = { id: theatersList.length + 1, ...body };
          theatersList.push(newTheater);
          return new Response(JSON.stringify(newTheater), { status: 200 });
        }
        return new Response(JSON.stringify(theatersList), { status: 200 });
      }
      if (path === "/admin/roles") {
        if (method === "POST") {
          const newRole = { id: rolesList.length + 1, ...body };
          rolesList.push(newRole);
          return new Response(JSON.stringify(newRole), { status: 200 });
        }
        return new Response(JSON.stringify(rolesList), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("基础配置")).toBeInTheDocument());
  fireEvent.click(screen.getByText("基础配置"));

  // Create theater
  fireEvent.change(screen.getByLabelText("剧场名称"), { target: { value: "西幽剧场" } });
  fireEvent.click(screen.getByText("周一早场"));
  fireEvent.click(screen.getByText("保存剧场"));

  // Create role
  fireEvent.change(screen.getByLabelText("角色名称"), { target: { value: "长离" } });
  fireEvent.change(screen.getByLabelText("角色分组"), { target: { value: "女位" } });
  fireEvent.click(screen.getByText("保存角色"));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/theaters",
      body: { name: "西幽剧场", default_weekly_template: { monday: ["early"] } },
    });
  });
  expect(requests).toContainEqual({
    method: "POST",
    path: "/admin/roles",
    body: { name: "长离", group_name: "女位" },
  });
});


test("actor entry and capability workflows", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  const actorsList: any[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = url.replace("http://localhost:8000", "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      if (method === "POST" || method === "PUT" || method === "PATCH") {
        requests.push({ method, path, body });
      }

      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/roles") {
        return new Response(JSON.stringify([{ id: 1, name: "长离", group_name: "女位" }]), { status: 200 });
      }
      if (path === "/admin/actors") {
        if (method === "POST") {
          const newActor = { id: 1, display_name: body.display_name, max_consecutive_performances: body.max_consecutive_performances, rating_level: body.rating_level, low_rating_monthly_cap: body.low_rating_monthly_cap, notes: body.notes, role_ids: [] };
          actorsList.push(newActor);
          return new Response(JSON.stringify(newActor), { status: 200 });
        }
        return new Response(JSON.stringify(actorsList), { status: 200 });
      }
      if (path === "/admin/actors/1") {
        if (method === "PATCH") {
          const actor = actorsList[0];
          actor.max_consecutive_performances = body.max_consecutive_performances;
          actor.rating_level = body.rating_level;
          actor.low_rating_monthly_cap = body.low_rating_monthly_cap;
          actor.notes = body.notes;
          return new Response(JSON.stringify(actor), { status: 200 });
        }
      }
      if (path === "/admin/actors/1/capabilities") {
        if (method === "PUT") {
          const actor = actorsList[0];
          actor.role_ids = body.role_ids;
          return new Response(JSON.stringify(actor), { status: 200 });
        }
      }
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("演员管理")).toBeInTheDocument());
  fireEvent.click(screen.getByText("演员管理"));

  // Fill and save actor
  fireEvent.change(screen.getByLabelText("演员姓名"), { target: { value: "小展" } });
  fireEvent.change(screen.getByLabelText("演员评级"), { target: { value: "normal" } });
  fireEvent.change(screen.getByLabelText("最大连场"), { target: { value: "2" } });
  fireEvent.click(screen.getByText("保存演员"));

  // Wait for the new row to render
  await screen.findByText("小展");

  // Edit fields
  fireEvent.change(screen.getByLabelText("修改最大连场"), { target: { value: "3" } });
  // Check role cap
  fireEvent.click(screen.getByLabelText("长离"));
  fireEvent.click(screen.getByText("保存演员设置"));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/actors",
      body: { display_name: "小展", max_consecutive_performances: 2, rating_level: "normal", low_rating_monthly_cap: null, notes: null },
    });
  });
  expect(requests).toContainEqual({
    method: "PATCH",
    path: "/admin/actors/1",
    body: { max_consecutive_performances: 3, rating_level: "normal", low_rating_monthly_cap: null, notes: null },
  });
  expect(requests).toContainEqual({
    method: "PUT",
    path: "/admin/actors/1/capabilities",
    body: { role_ids: [1] },
  });
});

