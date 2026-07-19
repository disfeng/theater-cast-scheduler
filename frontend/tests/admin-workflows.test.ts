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
  await fireEvent.update(screen.getByLabelText("邮箱或手机号"), "admin@example.com");
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
      if (path.startsWith("/admin/roles?")) return new Response(JSON.stringify(rolesList), { status: 200 });
      if (path.match(/^\/admin\/theaters\/\d+\/slots/)) return new Response(JSON.stringify([]), { status: 200 });
      if (path.match(/^\/admin\/theaters\/\d+\/weekly-template/)) return new Response(JSON.stringify({}), { status: 200 });
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  const app = await renderAdminRoute("/admin/settings");

  await fireEvent.click(screen.getByRole("button", { name: "新增剧场" }));
  await fireEvent.update(screen.getByLabelText("剧场名称"), "西幽剧场");
  await fireEvent.click(screen.getByRole("button", { name: "保存" }));

  await waitFor(() => expect(requests).toContainEqual({ method: "POST", path: "/admin/theaters", body: { name: "西幽剧场" } }));
  await fireEvent.click(await screen.findByRole("tab", { name: "剧场角色" }));
  await fireEvent.click(await screen.findByRole("button", { name: "新增角色" }));
  await fireEvent.update(screen.getByLabelText("角色名称"), "长离");
  await fireEvent.update(screen.getByLabelText("角色分组"), "女位");
  await fireEvent.click(screen.getByRole("button", { name: "保存" }));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/theaters",
      body: { name: "西幽剧场" },
    });
  });
  expect(requests).toContainEqual({
    method: "POST",
    path: "/admin/roles",
    body: { theater_id: 1, name: "长离", group_name: "女位" },
  });
});

test("settings groups theater configuration into focused tabs", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return new Response(JSON.stringify([{ id: 1, name: "西安幽州剧场", is_active: true }]), { status: 200 });
    if (path === "/admin/theaters/1/slots?include_inactive=false") return new Response(JSON.stringify([{ id: 1, theater_id: 1, name: "早场", start_time: "12:30:00", sort_order: 0, is_active: true }]), { status: 200 });
    if (path.startsWith("/admin/roles?") && path.includes("theater_id=1")) return new Response(JSON.stringify([
      { id: 1, theater_id: 1, name: "柳知雨", group_name: "女", is_active: true },
      { id: 2, theater_id: 1, name: "谢允昭", group_name: "男", is_active: true },
    ]), { status: 200 });
    if (path === "/admin/actors") return new Response(JSON.stringify([
      { id: 1, display_name: "小展", role_ids: [1] },
      { id: 2, display_name: "小雨", role_ids: [1, 2] },
      { id: 3, display_name: "小北", role_ids: [2] },
    ]), { status: 200 });
    if (path === "/admin/theaters/1/weekly-template") return new Response(JSON.stringify({ monday: [1] }), { status: 200 });
    return new Response(JSON.stringify([]), { status: 200 });
  }));

  const view = await renderAdminRoute("/admin/settings");

  expect(await screen.findByRole("button", { name: "新增场次" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "保存周模板" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "新增角色" })).not.toBeInTheDocument();

  await fireEvent.click(screen.getByRole("tab", { name: "默认周模板" }));
  expect(screen.getByRole("button", { name: "保存周模板" })).toBeVisible();
  expect(view.container.querySelectorAll(".template-day-card")).toHaveLength(7);

  await fireEvent.click(screen.getByRole("tab", { name: "剧场角色" }));
  expect(screen.getByRole("button", { name: "新增角色" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "出演演员" })).toBeVisible();
  expect(await screen.findByText("小展、小雨")).toBeVisible();
  await fireEvent.update(screen.getByLabelText("搜索角色或分组"), "女");
  expect(await screen.findByText("柳知雨")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("谢允昭")).not.toBeInTheDocument());
});

test("AI parser settings keep the stored mask separate from a replacement key", async () => {
  const requests: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters" || path === "/admin/actors") return new Response("[]");
    if (path === "/admin/system-settings/ai-parser" && (init?.method || "GET") === "GET") return new Response(JSON.stringify({ enabled: true, endpoint: "https://provider.example/v1", api_key_masked: "••••••••", model_name: "model-a", timeout_seconds: 12, prompt_version: "board-v1", last_test_ok: null, last_test_message: null, last_tested_at: null }));
    if (path === "/admin/system-settings/ai-parser" && init?.method === "PUT") { requests.push(JSON.parse(String(init.body))); return new Response(JSON.stringify({ enabled: true, endpoint: "https://provider.example/v1", api_key_masked: "••••••••", model_name: "model-b", timeout_seconds: 20, prompt_version: "board-v1", last_test_ok: null, last_test_message: null, last_tested_at: null })); }
    if (path.endsWith("/ai-parser/test")) { requests.push("tested"); return new Response(JSON.stringify({ ok: true, message: "connection_ok" })); }
    return new Response("[]");
  }));
  await renderAdminRoute("/admin/settings");
  await fireEvent.click(screen.getByRole("tab", { name: "系统设置" }));
  expect(await screen.findByText("已保存：••••••••")).toBeVisible();
  await fireEvent.update(screen.getByLabelText("模型名称"), "model-b");
  await fireEvent.update(screen.getByLabelText("API Key"), "replacement-secret");
  await fireEvent.click(screen.getByRole("button", { name: "保存 AI 配置" }));
  await waitFor(() => expect(requests[0].api_key).toBe("replacement-secret"));
  expect(requests[0]).not.toHaveProperty("api_key_masked");
  expect(requests[0]).not.toHaveProperty("prompt_version");
  expect(requests[0]).not.toHaveProperty("last_test_message");
  await waitFor(() => expect(screen.getByLabelText("API Key")).toHaveValue(""));
  await fireEvent.click(screen.getByRole("button", { name: "保存 AI 配置" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1]).not.toHaveProperty("api_key");
  await fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
  await waitFor(() => expect(requests).toContain("tested"));
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
      if (path === "/admin/theaters") {
        return new Response(JSON.stringify([
          { id: 1, name: "西安幽州剧场", is_active: true },
          { id: 2, name: "长安剧场", is_active: true },
        ]), { status: 200 });
      }
      if (path === "/admin/roles") {
        return new Response(JSON.stringify([
          { id: 1, theater_id: 1, name: "长离", group_name: "女位", is_active: true },
          { id: 2, theater_id: 2, name: "柳知雨", group_name: "女位", is_active: true },
        ]), { status: 200 });
      }
      if (path === "/admin/actors") {
        if (method === "POST") {
          const newActor = { id: 1, display_name: body.display_name, phone_number: body.phone_number, theater_ids: body.theater_ids, entry_theater_id: body.entry_theater_id, max_consecutive_performances: body.max_consecutive_performances, rating_level: body.rating_level, low_rating_monthly_cap: body.low_rating_monthly_cap, notes: body.notes, role_ids: [] };
          actorsList.push(newActor);
          return new Response(JSON.stringify({ actor: newActor, credential_delivery: { username: body.phone_number, initial_password: "Abc123456789", filename: "西安幽州剧场-小展.pdf", pdf_base64: "JVBERg==" } }), { status: 200 });
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

  await fireEvent.click(screen.getByRole("button", { name: "新增演员" }));
  expect(screen.getByRole("dialog", { name: "新增演员" })).toBeVisible();
  await fireEvent.update(screen.getByLabelText("演员姓名"), "小展");
  await fireEvent.update(screen.getByLabelText("手机号"), "13800138000");
  await fireEvent.update(screen.getByLabelText("最大连场"), "2");
  await fireEvent.click(await screen.findByRole("checkbox", { name: "西安幽州剧场：长离" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));

  await screen.findByText("小展");
  expect(screen.getByRole("columnheader", { name: "可出演角色" })).toBeVisible();
  expect(await screen.findByText("西安幽州剧场：长离")).toBeVisible();

  await fireEvent.update(screen.getByLabelText("搜索演员"), "不存在");
  await waitFor(() => expect(screen.queryByText("小展")).not.toBeInTheDocument());
  await fireEvent.update(screen.getByLabelText("搜索演员"), "小展");
  expect(await screen.findByText("小展")).toBeVisible();

  await fireEvent.click(screen.getByRole("button", { name: "编辑小展" }));
  expect(screen.getByRole("dialog", { name: "编辑演员" })).toBeVisible();
  await fireEvent.update(screen.getByLabelText("最大连场"), "3");
  await fireEvent.click(await screen.findByRole("checkbox", { name: "长安剧场：柳知雨" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));

  await waitFor(() => {
    expect(requests).toContainEqual({
      method: "POST",
      path: "/admin/actors",
      body: { display_name: "小展", phone_number: "13800138000", theater_ids: [1], entry_theater_id: 1, max_consecutive_performances: 2, rating_level: "normal", low_rating_monthly_cap: null, notes: null },
    });
    expect(requests).toContainEqual({
      method: "PUT",
      path: "/admin/actors/1/capabilities",
      body: { role_ids: [1] },
    });
    expect(requests).toContainEqual({
      method: "PATCH",
      path: "/admin/actors/1",
      body: { phone_number: "13800138000", theater_ids: [1, 2], entry_theater_id: 1, max_consecutive_performances: 3, rating_level: "normal", low_rating_monthly_cap: null, notes: null },
    });
    expect(requests).toContainEqual({
      method: "PUT",
      path: "/admin/actors/1/capabilities",
      body: { role_ids: [1, 2] },
    });
  });
});
