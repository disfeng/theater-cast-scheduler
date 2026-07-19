import { fireEvent } from "@testing-library/vue";
import { expect, test } from "vitest";
import { readFileSync } from "node:fs";
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
  expect(items.length).toBe(8);
  expect(icons.length).toBe(items.length);
});

test("actor navigation gives every menu item an icon", async () => {
  const { container } = await renderActorRoute("/actor/leave");
  const items = container.querySelectorAll(".sidebar-menu .el-menu-item");
  const icons = container.querySelectorAll(".sidebar-menu .el-menu-item .el-icon");
  expect(items.length).toBe(2);
  expect(icons.length).toBe(items.length);
});

test("collapsed sidebar centers its brand and menu icons on one axis", async () => {
  const { container } = await renderAdminRoute("/admin/weekly-scheduling");
  await fireEvent.click(container.querySelector<HTMLButtonElement>('[aria-label="切换导航"]')!);

  expect(container.querySelector(".sidebar")).toHaveClass("is-collapsed");
  const source = vueSources["../src/layouts/AppShell.vue"];
  expect(source).toContain(".sidebar.is-collapsed .brand");
  expect(source).toContain(".sidebar-menu.el-menu--collapse");
  expect(source).toContain("justify-content: center");
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

test("light workspace content and form controls do not keep dark-theme white text", () => {
  const offenders = Object.entries(vueSources).flatMap(([path, source]) => {
    const matches = source.match(/<(?:div|h[1-6]|td|input|select|textarea)\b[^>]*style="[^"]*color:\s*#fff\b[^"]*"/gi);
    return matches?.map(() => path) ?? [];
  });
  expect(offenders).toEqual([]);
});

test("admin pages use one full-width content alignment inside the shell padding", () => {
  const shell = vueSources["../src/layouts/AppShell.vue"];
  expect(shell).toContain(".workspace-main { padding: 28px;");
  expect(shell).toContain(".workspace-main { padding: 18px 14px;");

  const adminPages = Object.entries(vueSources).filter(([path]) => path.includes("/pages/admin/"));
  const constrained = adminPages.flatMap(([path, source]) =>
    /(?:settings|actors|monthly|scheduling)-page\s*\{[^}]*max-width:\s*\d+px/.test(source) ? [path] : [],
  );
  expect(constrained).toEqual([]);
  for (const page of ["DashboardPage.vue", "DesignationWishPage.vue", "RequestsPage.vue"]) {
    const source = Object.entries(vueSources).find(([path]) => path.endsWith(page))?.[1];
    expect(source).toContain('class="page-container"');
  }
});

test("weekly scheduling uses the original single-week role matrix", () => {
  const source = vueSources["../src/pages/admin/WeeklySchedulingPage.vue"];
  expect(source).not.toContain(".toolbar-primary::after");
  expect(source).toContain('class="schedule-matrix"');
  expect(source).toContain('class="matrix-scroll"');
  expect(source).not.toContain('class="month-weeks"');
});

test("global dialog system defines shared form and semantic confirmation styles", () => {
  const baseStyles = readFileSync(`${process.cwd()}/src/styles/base.css`, "utf8");
  expect(baseStyles).toContain(".app-dialog");
  expect(baseStyles).toContain(".app-message-box--warning");
  expect(baseStyles).toContain(".app-message-box--danger");
});

test("all application dialogs and confirmations use the shared dialog system", () => {
  const dialogs = Object.entries(vueSources).flatMap(([path, source]) =>
    (source.match(/<el-dialog\b[^>]*>/g) ?? []).map((tag) => ({ path, tag })),
  );
  expect(dialogs.filter(({ tag }) => !/class="[^"]*app-dialog/.test(tag))).toEqual([]);

  const directMessageBoxes = Object.entries(vueSources)
    .filter(([, source]) => /ElMessageBox\.(?:confirm|alert)\(/.test(source))
    .map(([path]) => path);
  expect(directMessageBoxes).toEqual([]);
});
