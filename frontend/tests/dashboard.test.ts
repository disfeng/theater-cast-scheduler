import { expect, test, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/vue";
import { renderAdminRoute } from "./helpers/render-app";

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

function installAdminFetch(data: {
  actors?: any[];
  leaves?: any[];
  batches?: any[];
  theaters?: any[];
}) {
  const requests: { method: string; path: string; body: any }[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;

      requests.push({ method, path, body });

      if (path === "/auth/login") {
        return new Response(JSON.stringify({ access_token: "admin-token", role: "admin" }), { status: 200 });
      }
      if (path === "/admin/actors") {
        return new Response(JSON.stringify(data.actors || []), { status: 200 });
      }
      if (path === "/admin/leave-requests") {
        return new Response(JSON.stringify(data.leaves || []), { status: 200 });
      }
      if (path === "/admin/weekly-batches") {
        return new Response(JSON.stringify(data.batches || []), { status: 200 });
      }
      if (path === "/admin/theaters") {
        return new Response(JSON.stringify(data.theaters || []), { status: 200 });
      }
      if (path.startsWith("/admin/leave-requests/") && path.endsWith("/review")) {
        return new Response(JSON.stringify({ id: 4, actor_name: "小展", status: "approved" }), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    })
  );

  return { requests };
}

test("dashboard summarizes operational data and approves leave", async () => {
  const mock = installAdminFetch({
    actors: [{ id: 1 }],
    leaves: [{ id: 4, actor_name: "小展", status: "pending" }],
    batches: [{ id: 3, status: "draft" }]
  });
  const app = await renderAdminRoute("/admin/dashboard");
  expect(await screen.findByText("1", { selector: "[data-metric='actors']" })).toBeInTheDocument();
  expect(screen.getByText("小展")).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button", { name: "批准小展的请假" }));
  expect(mock.requests).toContainEqual(expect.objectContaining({
    path: "/admin/leave-requests/4/review",
    body: { status: "approved" }
  }));
  app.unmount();
});
