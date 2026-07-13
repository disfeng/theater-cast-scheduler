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
