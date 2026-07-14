import ElementPlus from "element-plus";
import { fireEvent, render, screen } from "@testing-library/vue";
import { expect, test } from "vitest";
import MonthlyCalendarEditor from "../src/components/admin/MonthlyCalendarEditor.vue";

test("toggles slots, closes a day, and restores its weekly template", async () => {
  const result = render(MonthlyCalendarEditor, {
    props: {
      year: 2026,
      month: 8,
      slots: [
        { id: 1, theater_id: 1, name: "早场", start_time: "10:00:00", sort_order: 0, is_active: true },
        { id: 2, theater_id: 1, name: "晚场", start_time: "19:00:00", sort_order: 1, is_active: true },
      ],
      weeklyTemplate: { monday: [1, 2] },
      modelValue: { "2026-08-03": [1, 2] },
      persistedDates: [],
    },
    global: { plugins: [ElementPlus] },
  });
  const updateAt = (index: number) => (
    (result.emitted("update:modelValue") as unknown[][])[index][0] as Record<string, number[]>
  );

  await fireEvent.click(screen.getByRole("button", { name: "8月3日 关闭早场" }));
  expect(updateAt(0)["2026-08-03"]).toEqual([2]);

  await fireEvent.click(screen.getByRole("button", { name: "8月3日 设为闭店" }));
  expect(updateAt(1)["2026-08-03"]).toEqual([]);

  await result.rerender({ modelValue: { "2026-08-03": [] } });
  await fireEvent.click(screen.getByRole("button", { name: "8月3日 按模板恢复" }));
  expect(updateAt(2)["2026-08-03"]).toEqual([1, 2]);
});

test("distinguishes closed, persisted, and unsaved template dates", () => {
  render(MonthlyCalendarEditor, {
    props: {
      year: 2026,
      month: 8,
      slots: [
        { id: 1, theater_id: 1, name: "早场", start_time: "10:00:00", sort_order: 0, is_active: true },
      ],
      weeklyTemplate: { monday: [1] },
      modelValue: {
        "2026-08-03": [],
        "2026-08-04": [1],
        "2026-08-05": [1],
      },
      persistedDates: ["2026-08-03", "2026-08-04"],
    },
    global: { plugins: [ElementPlus] },
  });

  const closedCell = screen.getByRole("button", { name: "8月3日 开启早场" }).closest(".day-cell");
  const persistedCell = screen.getByRole("button", { name: "8月4日 关闭早场" }).closest(".day-cell");
  const templateCell = screen.getByRole("button", { name: "8月5日 关闭早场" }).closest(".day-cell");

  expect(closedCell).toHaveClass("is-closed");
  expect(closedCell).not.toHaveClass("is-persisted");
  expect(persistedCell).toHaveClass("is-persisted");
  expect(templateCell).not.toHaveClass("is-persisted");
  expect(closedCell?.querySelector(".el-tag--danger")).toBeInTheDocument();
});

test("shows a compact legend for the three calendar states", () => {
  render(MonthlyCalendarEditor, {
    props: {
      year: 2026,
      month: 8,
      slots: [],
      weeklyTemplate: {},
      modelValue: {},
      persistedDates: [],
    },
    global: { plugins: [ElementPlus] },
  });

  const legend = screen.getByLabelText("日历状态图例");
  expect(legend).toHaveTextContent("已保存");
  expect(legend).toHaveTextContent("闭店");
  expect(legend).toHaveTextContent("模板待保存");
});
