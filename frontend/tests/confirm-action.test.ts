import { beforeEach, expect, test, vi } from "vitest";

const { confirm, alert } = vi.hoisted(() => ({ confirm: vi.fn(), alert: vi.fn() }));

vi.mock("element-plus", () => ({
  ElMessageBox: { confirm, alert },
}));

import { confirmAction } from "../src/features/dialogs/confirm-action";

beforeEach(() => {
  confirm.mockReset().mockResolvedValue("confirm");
  alert.mockReset().mockResolvedValue("confirm");
});

test("warning confirmation uses the shared semantic class and labels", async () => {
  await confirmAction({
    title: "放弃修改",
    message: "尚未保存的内容将丢失。",
    tone: "warning",
    confirmButtonText: "确认放弃",
    cancelButtonText: "继续编辑",
  });

  expect(confirm).toHaveBeenCalledWith("尚未保存的内容将丢失。", "放弃修改", expect.objectContaining({
    type: "warning",
    customClass: "app-message-box app-message-box--warning",
    confirmButtonText: "确认放弃",
    cancelButtonText: "继续编辑",
  }));
});

test("danger alert uses alert mode without a cancel button", async () => {
  await confirmAction({ title: "无法发布", message: "请先补齐角色。", tone: "danger", alert: true, confirmButtonText: "返回补充" });
  expect(alert).toHaveBeenCalledWith("请先补齐角色。", "无法发布", expect.objectContaining({ type: "error", customClass: "app-message-box app-message-box--danger", confirmButtonText: "返回补充" }));
  expect(confirm).not.toHaveBeenCalled();
});
