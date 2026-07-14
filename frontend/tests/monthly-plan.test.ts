import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/vue";
import { renderAdminRoute } from "./helpers/render-app";

const theater = { id: 1, name: "西安幽州剧场", is_active: true };
const slots = [
  { id: 1, theater_id: 1, name: "早场", start_time: "10:00:00", sort_order: 0, is_active: true },
  { id: 2, theater_id: 1, name: "晚场", start_time: "19:00:00", sort_order: 1, is_active: true },
];

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 6, 14));
});

afterEach(() => cleanup());

function performance(performanceDate: string, slotId = 1) {
  const slot = slots.find((item) => item.id === slotId)!;
  return {
    id: slotId,
    theater_id: 1,
    performance_date: performanceDate,
    theater_slot_id: slotId,
    slot_name_snapshot: slot.name,
    start_time_snapshot: slot.start_time,
    status: "draft",
  };
}

function mockApi(
  onReplace?: (body: any) => void,
  replaceConflict = false,
  existingPerformances: ReturnType<typeof performance>[] = [],
  replacementPerformances: ReturnType<typeof performance>[] = [],
) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    const method = init?.method || "GET";
    if (path === "/admin/theaters") return new Response(JSON.stringify([theater]), { status: 200 });
    if (path === "/admin/theaters/1/slots?include_inactive=false") return new Response(JSON.stringify(slots), { status: 200 });
    if (path === "/admin/theaters/1/weekly-template") return new Response(JSON.stringify({ monday: [1, 2] }), { status: 200 });
    if (path.startsWith("/admin/performances?")) return new Response(JSON.stringify(existingPerformances), { status: 200 });
    if (path === "/admin/monthly-plan" && method === "PUT") {
      if (replaceConflict) return new Response(JSON.stringify({ detail: "monthly_plan_has_referenced_performances" }), { status: 409 });
      const body = JSON.parse(String(init?.body));
      onReplace?.(body);
      return new Response(JSON.stringify(replacementPerformances), { status: 200 });
    }
    return new Response(JSON.stringify([]), { status: 200 });
  }));
}

test("defaults to next month and saves the edited calendar", async () => {
  let replaceBody: any;
  mockApi((body) => { replaceBody = body; });
  await renderAdminRoute("/admin/monthly-plan");

  expect(await screen.findByText("2026年8月")).toBeInTheDocument();
  await fireEvent.click(await screen.findByRole("button", { name: "8月3日 关闭早场" }));
  await fireEvent.click(screen.getByRole("button", { name: "生成月度计划" }));

  await waitFor(() => expect(replaceBody).toBeTruthy());
  expect(replaceBody.theater_id).toBe(1);
  expect(replaceBody.year).toBe(2026);
  expect(replaceBody.month).toBe(8);
  expect(replaceBody.days).toContainEqual({ performance_date: "2026-08-03", theater_slot_ids: [2] });
});

test("marks performances loaded from the backend as persisted", async () => {
  mockApi(undefined, false, [performance("2026-08-04")]);
  await renderAdminRoute("/admin/monthly-plan");

  const persistedCell = (await screen.findByRole("button", { name: "8月4日 关闭早场" })).closest(".day-cell");
  expect(persistedCell).toHaveClass("is-persisted");
});

test("marks template dates as persisted only after a successful save", async () => {
  mockApi(undefined, false, [], [performance("2026-08-03"), performance("2026-08-03", 2)]);
  await renderAdminRoute("/admin/monthly-plan");

  const templateCell = (await screen.findByRole("button", { name: "8月3日 关闭早场" })).closest(".day-cell");
  expect(templateCell).not.toHaveClass("is-persisted");

  await fireEvent.click(screen.getByRole("button", { name: "生成月度计划" }));
  await waitFor(() => expect(templateCell).toHaveClass("is-persisted"));
});

test("switches to the next month from the calendar toolbar", async () => {
  mockApi();
  await renderAdminRoute("/admin/monthly-plan");
  await screen.findByText("2026年8月");
  await fireEvent.click(screen.getByRole("button", { name: "下一月" }));
  expect(await screen.findByText("2026年9月")).toBeInTheDocument();
});

test("shows a readable conflict without discarding the draft", async () => {
  mockApi(undefined, true);
  await renderAdminRoute("/admin/monthly-plan");
  await screen.findByRole("button", { name: "8月3日 关闭早场" });
  await fireEvent.click(screen.getByRole("button", { name: "生成月度计划" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("该月存在已排班或已指定场次，请先处理引用。");
});
