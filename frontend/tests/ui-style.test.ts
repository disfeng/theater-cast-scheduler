import { expect, test } from "vitest";
import { renderActorRoute, renderAdminRoute } from "./helpers/render-app";

const vueSources = import.meta.glob("../src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

test("admin navigation gives every menu item an icon", async () => {
  const { container } = await renderAdminRoute("/admin/weekly-scheduling");
  const items = container.querySelectorAll(".sidebar-menu .el-menu-item");
  const icons = container.querySelectorAll(".sidebar-menu .el-menu-item .el-icon");
  expect(items.length).toBe(7);
  expect(icons.length).toBe(items.length);
});

test("actor navigation gives every menu item an icon", async () => {
  const { container } = await renderActorRoute("/actor/leave");
  const items = container.querySelectorAll(".sidebar-menu .el-menu-item");
  const icons = container.querySelectorAll(".sidebar-menu .el-menu-item .el-icon");
  expect(items.length).toBe(2);
  expect(icons.length).toBe(items.length);
});

test("light secondary buttons do not retain low-contrast dark-theme text", () => {
  const offenders = Object.entries(vueSources).flatMap(([path, source]) => {
    const buttons = source.match(/<button\b[\s\S]*?<\/button>/gi) ?? [];
    return buttons.flatMap((button) => {
      const style = button.match(/style="([^"]*)"/i)?.[1] ?? "";
      const alpha = Number(style.match(/background:\s*rgba\([^)]*,\s*(0?\.\d+)\s*\)/i)?.[1]);
      const hasLightText = /color:\s*(?:#34d399|#f87171|#fff|white)\b/i.test(style);
      return Number.isFinite(alpha) && alpha <= 0.25 && hasLightText ? [path] : [];
    });
  });
  expect(offenders).toEqual([]);
});
