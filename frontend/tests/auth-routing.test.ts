// frontend/tests/auth-routing.test.ts
import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderApp } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("login identifier accepts actor phone numbers", async () => {
  const app = await renderApp("/login");
  const identifier = screen.getByLabelText("邮箱或手机号");
  expect(identifier).toHaveAttribute("type", "text");
  await fireEvent.update(identifier, "18627912251");
  expect(identifier).toHaveValue("18627912251");
  app.unmount();
});

test("admin login changes the URL and refresh restores the route", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "t", role: "admin" }), { status: 200 })));
  const first = await renderApp("/login");
  await fireEvent.update(screen.getByLabelText("邮箱或手机号"), "admin@example.com");
  await fireEvent.update(screen.getByLabelText("密码"), "secret");
  await fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await waitFor(() => expect(first.router.currentRoute.value.fullPath).toBe("/admin/dashboard"));
  first.unmount();
  const second = await renderApp("/admin/actors");
  await waitFor(() => expect(second.router.currentRoute.value.fullPath).toBe("/admin/actors"));
});

test("actor cannot enter an admin route", async () => {
  localStorage.setItem("token", "t"); localStorage.setItem("role", "actor");
  const app = await renderApp("/admin/dashboard");
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/actor/schedule"));
});

test("actor must change the initial password before entering the workspace", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/auth/login") return Response.json({ access_token: "initial-token", role: "actor", must_change_password: true });
    if (path === "/actor/me/password" && init?.method === "POST") return Response.json({ access_token: "ready-token", role: "actor", must_change_password: false });
    if (path === "/actor/me/schedule") return Response.json([]);
    return Response.json({});
  }));

  const app = await renderApp("/login");
  await fireEvent.update(screen.getByLabelText("邮箱或手机号"), "13800138000");
  await fireEvent.update(screen.getByLabelText("密码"), "Initial123456");
  await fireEvent.click(screen.getByRole("button", { name: "登录" }));

  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/actor/change-password"));
  expect(screen.getByRole("heading", { name: "首次登录，请修改密码" })).toBeVisible();

  await fireEvent.update(screen.getByLabelText("当前密码"), "Initial123456");
  await fireEvent.update(screen.getByLabelText("新密码"), "Secure123456");
  await fireEvent.update(screen.getByLabelText("确认新密码"), "Secure123456");
  await fireEvent.click(screen.getByRole("button", { name: "确认修改" }));

  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/actor/schedule"));
  expect(localStorage.getItem("token")).toBe("ready-token");
  expect(localStorage.getItem("must_change_password")).toBe("false");
});

test("login returns an admin to the originally requested page", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "t", role: "admin" }), { status: 200 })));
  const app = await renderApp("/admin/actors");
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toContain("/login?redirect="));
  await fireEvent.update(screen.getByLabelText("邮箱或手机号"), "admin@example.com");
  await fireEvent.update(screen.getByLabelText("密码"), "secret");
  await fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toBe("/admin/actors"));
});

test("unknown paths redirect according to the current session", async () => {
  const guest = await renderApp("/missing");
  await waitFor(() => expect(guest.router.currentRoute.value.path).toBe("/login"));
  guest.unmount();

  localStorage.setItem("token", "t");
  localStorage.setItem("role", "admin");
  const admin = await renderApp("/also-missing");
  await waitFor(() => expect(admin.router.currentRoute.value.path).toBe("/admin/dashboard"));
});
