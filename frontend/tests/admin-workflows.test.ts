import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderApp, renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("admin shell exposes settings and actor management pages", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  const app = await renderApp("/login");
  await fireEvent.update(screen.getByLabelText("邮箱"), "admin@example.com");
  await fireEvent.update(screen.getByLabelText("密码"), "secret");
  await fireEvent.click(screen.getByRole("button", { name: "登录" }));

  await waitFor(() => expect(screen.getByText("基础配置")).toBeInTheDocument());
  await fireEvent.click(screen.getByText("基础配置"));
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/admin/settings"));

  await fireEvent.click(screen.getByText("演员管理"));
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/admin/actors"));
});

test("theater and role entry workflows", async () => {
  const requests: { method: string; path: string; body: any }[] = [];
  const theatersList: any[] = [];
  const rolesList: any[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
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
    })
  );

  const app = await renderAdminRoute("/admin/settings");

  // Create theater
  await fireEvent.update(screen.getByLabelText("剧场名称"), "西幽剧场");
  await fireEvent.click(screen.getByRole("checkbox", { name: "周一下午场" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存剧场" }));

  // Create role
  await fireEvent.update(screen.getByLabelText("角色名称"), "长离");
  await fireEvent.update(screen.getByLabelText("角色分组"), "女位");
  await fireEvent.click(screen.getByRole("button", { name: "保存角色" }));

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
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
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
    })
  );

  const app = await renderAdminRoute("/admin/actors");

  // Fill and save actor
  await fireEvent.update(screen.getByLabelText("演员姓名"), "小展");
  await fireEvent.update(screen.getByLabelText("演员评级"), "normal");
  await fireEvent.update(screen.getByLabelText("最大连场"), "2");
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));

  // Wait for the new row to render
  await screen.findByText("小展");

  // Edit fields
  await fireEvent.update(screen.getByLabelText("修改最大连场"), "3");
  // Check capability role checkbox
  await fireEvent.click(screen.getByRole("checkbox", { name: "长离" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存演员设置" }));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/actors",
      body: { display_name: "小展", max_consecutive_performances: 2, rating_level: "normal", low_rating_monthly_cap: null, notes: null },
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
});
