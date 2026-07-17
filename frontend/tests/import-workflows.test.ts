import { screen } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

test("旧周批次导入不再作为新指定与许愿的前端入口", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/theaters") return Response.json([{ id: 1, name: "西幽剧场", is_active: true }]);
    if (path.startsWith("/admin/designation-workspace/month")) return Response.json({ theater_id: 1, year: 2026, month: 7, totals: { players: 0, designations: 0, wishes: 0, pending: 0, conflicts: 0 }, days: [] });
    return Response.json({ detail: path }, { status: 500 });
  }));
  await renderAdminRoute("/admin/designations-wishes?theater_id=1&year=2026&month=7");
  expect(await screen.findByRole("heading", { name: "指定与许愿" })).toBeInTheDocument();
  expect(screen.queryByText("周批次管理")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "创建/打开批次" })).not.toBeInTheDocument();
});
