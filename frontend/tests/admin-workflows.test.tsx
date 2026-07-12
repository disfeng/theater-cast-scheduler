import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { expect, test, vi } from "vitest";
import App from "../src/App";

test("admin shell exposes settings and actor management pages", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) {
        return new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 });
      }
      if (url.endsWith("/admin/theaters")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/roles")) return new Response(JSON.stringify([]), { status: 200 });
      if (url.endsWith("/admin/actors")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );

  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("基础配置")).toBeInTheDocument());
  fireEvent.click(screen.getByText("基础配置"));
  expect(await screen.findByText("剧场配置")).toBeInTheDocument();
  fireEvent.click(screen.getByText("演员管理"));
  expect(await screen.findByText("新增演员")).toBeInTheDocument();
});
