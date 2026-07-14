// frontend/tests/api-client.test.ts
import { beforeEach, expect, test, vi } from "vitest";
import { ApiClient, ApiError } from "../src/api/client";

beforeEach(() => vi.restoreAllMocks());

test("normalizes FastAPI validation errors", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    detail: [{ loc: ["body", "month"], msg: "Input should be less than or equal to 12" }],
  }), { status: 422 })));
  const client = new ApiClient("");
  await expect(client.request("/admin/monthly-plan/generate", {
    method: "POST", token: "token", body: { month: 13 },
  })).rejects.toEqual(expect.objectContaining({
    status: 422,
    message: "body.month: Input should be less than or equal to 12",
  }));
});
