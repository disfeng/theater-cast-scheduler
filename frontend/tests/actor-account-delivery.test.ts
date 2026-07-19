import { fireEvent, render, screen } from "@testing-library/vue";
import ElementPlus from "element-plus";
import { beforeEach, expect, test, vi } from "vitest";
import ActorFormDrawer from "../src/components/admin/ActorFormDrawer.vue";

beforeEach(() => vi.restoreAllMocks());

test("新增演员要求手机号和入职剧场并交付 PDF", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors" && init?.method === "POST") {
      return Response.json({
        actor: { id: 7, display_name: "小A", phone_number: "13800138000", theater_ids: [2], entry_theater_id: 2, role_ids: [] },
        credential_delivery: { username: "13800138000", initial_password: "Abc123456789", filename: "西安幽州剧场-小A.pdf", pdf_base64: "JVBERg==" },
      });
    }
    if (path === "/admin/actors/7/capabilities") return Response.json({ id: 7, role_ids: [] });
    return Response.json({});
  }));
  const view = render(ActorFormDrawer, {
    props: { modelValue: false, actor: null, token: "token", theaters: [{ id: 2, name: "西安幽州剧场", is_active: true }], roles: [] },
    global: { plugins: [ElementPlus] },
  });
  await view.rerender({ modelValue: true });
  expect(screen.getByRole("textbox", { name: "手机号" })).toBeRequired();
  expect(screen.getByRole("combobox", { name: "入职剧场" })).toBeInTheDocument();
  await fireEvent.update(screen.getByLabelText("演员姓名"), "小A");
  await fireEvent.update(screen.getByLabelText("手机号"), "13800138000");
  await fireEvent.click(screen.getByLabelText("所属剧场：西安幽州剧场"));
  await fireEvent.click(screen.getByRole("combobox", { name: "入职剧场" }));
  await fireEvent.click(await screen.findByText("西安幽州剧场", { selector: ".el-select-dropdown__item span" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));
  expect(await screen.findByRole("dialog", { name: "演员账号已创建" })).toBeVisible();
  expect(screen.getByText("13800138000")).toBeVisible();
  expect(screen.getByRole("button", { name: "下载账号 PDF" })).toBeVisible();
});
