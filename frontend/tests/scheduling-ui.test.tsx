import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { expect, test, vi } from "vitest";
import App from "../src/App";

test("renders login screen by default", () => {
  render(<App />);
  expect(screen.getByText("剧场卡司排班")).toBeInTheDocument();
  expect(screen.getByLabelText("邮箱")).toBeInTheDocument();
});

test("admin can see weekly scheduling navigation after login", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ access_token: "token", role: "admin" }), { status: 200 })),
  );
  render(<App />);
  fireEvent.click(screen.getByText("登录"));
  await waitFor(() => expect(screen.getByText("周排班")).toBeInTheDocument());
});
