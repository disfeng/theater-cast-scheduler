// frontend/tests/auth-routing.test.ts
import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/vue";
import { renderApp } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("admin login changes the URL and refresh restores the route", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "t", role: "admin" }), { status: 200 })));
  const first = await renderApp("/login");
  await fireEvent.update(screen.getByLabelText("邮箱"), "admin@example.com");
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

test("login returns an admin to the originally requested page", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ access_token: "t", role: "admin" }), { status: 200 })));
  const app = await renderApp("/admin/actors");
  await waitFor(() => expect(app.router.currentRoute.value.fullPath).toContain("/login?redirect="));
  await fireEvent.update(screen.getByLabelText("邮箱"), "admin@example.com");
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
