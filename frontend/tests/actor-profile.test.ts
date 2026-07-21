import { beforeEach, expect, test, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/vue";
import { renderActorRoute } from "./helpers/render-app";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

test("actor profile presents identity, theaters, shortcuts and account security", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/actor/me/profile") {
      return Response.json({
        id: 1,
        display_name: "小A",
        phone_number: "18627912251",
        must_change_password: false,
        theaters: [
          { id: 2, name: "西安幽州剧场", is_entry_theater: true },
          { id: 3, name: "长安剧场", is_entry_theater: false },
        ],
      });
    }
    return Response.json([]);
  }));

  await renderActorRoute("/actor/profile");

  expect(await screen.findByRole("heading", { name: "我的" })).toBeVisible();
  expect(await screen.findByText("186****2251")).toBeVisible();
  expect(screen.getAllByText("小A").length).toBeGreaterThan(0);
  expect(screen.getByText("账号正常")).toBeVisible();
  expect(screen.getByText("西安幽州剧场")).toBeVisible();
  expect(screen.getByText("主剧场")).toBeVisible();
  expect(screen.getByText("长安剧场")).toBeVisible();
  const shortcuts = within(screen.getByRole("navigation", { name: "我的常用功能" }));
  expect(shortcuts.getByRole("link", { name: /修改密码/ })).toHaveAttribute("href", "/actor/change-password");
  expect(shortcuts.getByRole("link", { name: /演出日历/ })).toHaveAttribute("href", "/actor/calendar");
  expect(shortcuts.getByRole("link", { name: /我的请假/ })).toHaveAttribute("href", "/actor/leave");
  expect(screen.getByText("页面已启用动态水印")).toBeVisible();
  expect(screen.getByRole("button", { name: "退出登录" })).toBeVisible();

  await waitFor(() => expect(fetch).toHaveBeenCalled());
});
