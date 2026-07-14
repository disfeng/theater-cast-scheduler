import { screen } from "@testing-library/vue";
import { expect, test } from "vitest";
import { renderAdminRoute } from "./helpers/render-app";

test("weekly scheduling preserves the existing explanatory surface", async () => {
  const app = await renderAdminRoute("/admin/weekly-scheduling");

  expect(await screen.findByRole("heading", { name: "周排班" })).toBeInTheDocument();
  expect(screen.getByText("锁定关键卡司，生成补排，查看指定失败和硬规则冲突。")).toBeInTheDocument();
  expect(screen.getByText("排班表区域")).toBeInTheDocument();
  expect(app.router.currentRoute.value.fullPath).toBe("/admin/weekly-scheduling");
});
