import { fireEvent, screen, waitFor } from "@testing-library/vue";
import { beforeEach, expect, test, vi } from "vitest";

import { renderAdminRoute } from "./helpers/render-app";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      if (path === "/admin/entitlements/reconciliation") {
        return Response.json({
          generated_at: "2026-07-17T00:00:00",
          expiry_filter: null,
          filtered_totals: {},
          global_totals: {},
          anomaly_count: 0,
          rows: [],
        });
      }
      if (path === "/admin/entitlement-item-types" || path === "/admin/entitlement-grant-batches") {
        return Response.json([]);
      }
      if (["/admin/theaters", "/admin/actors", "/admin/roles"].includes(path)) {
        return Response.json([]);
      }
      return Response.json({ detail: `unexpected:${path}` }, { status: 500 });
    }),
  );
});

test("separates entitlement management from designation and wish work", async () => {
  const view = await renderAdminRoute("/admin/entitlements");

  expect(await screen.findByRole("heading", { name: "权益管理" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "月度发放" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "权益背包" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "权益流水核对" })).toBeInTheDocument();

  await view.router.push("/admin/designations-wishes");
  expect(await screen.findByRole("heading", { name: "指定与许愿" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "月度发放" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "权益背包" })).not.toBeInTheDocument();
});

test("entitlement tabs survive a page refresh through the query string", async () => {
  const view = await renderAdminRoute("/admin/entitlements?tab=inventory");

  expect(await screen.findByRole("tab", { name: "权益背包" })).toHaveAttribute("aria-selected", "true");
  await fireEvent.click(screen.getByRole("tab", { name: "权益流水核对" }));
  await waitFor(() => expect(view.router.currentRoute.value.query.tab).toBe("reconciliation"));
});
