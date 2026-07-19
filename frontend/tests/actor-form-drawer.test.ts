import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import ElementPlus from "element-plus";
import ActorFormDrawer from "../src/components/admin/ActorFormDrawer.vue";

beforeEach(() => vi.restoreAllMocks());

test("capability retry does not duplicate a newly created actor", async () => {
  const requests: { method: string; path: string }[] = [];
  let capabilityAttempts = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    const method = init?.method || "GET";
    requests.push({ method, path });
    if (path === "/admin/actors" && method === "POST") {
      return new Response(JSON.stringify({
        actor: { id: 7, display_name: "小展", role_ids: [] },
        credential_delivery: { username: "13800138000", initial_password: "Abc123456789", filename: "西安幽州剧场-小展.pdf", pdf_base64: "JVBERg==" },
      }), { status: 200 });
    }
    if (path === "/admin/actors/7/capabilities" && method === "PUT") {
      capabilityAttempts += 1;
      if (capabilityAttempts === 1) return new Response(JSON.stringify({ detail: "角色能力保存失败" }), { status: 500 });
      return new Response(JSON.stringify({ id: 7, display_name: "小展", role_ids: [1] }), { status: 200 });
    }
    return new Response(JSON.stringify({}), { status: 200 });
  }));

  const view = render(ActorFormDrawer, {
    props: {
      modelValue: false,
      actor: null,
      token: "token",
      theaters: [{ id: 1, name: "西安幽州剧场", is_active: true }],
      roles: [{ id: 1, theater_id: 1, name: "长离", group_name: "女位", is_active: true }],
    },
    global: { plugins: [ElementPlus] },
  });

  await view.rerender({ modelValue: true });
  await fireEvent.update(screen.getByLabelText("演员姓名"), "小展");
  await fireEvent.update(screen.getByLabelText("手机号"), "13800138000");
  await fireEvent.click(screen.getByLabelText("所属剧场：西安幽州剧场"));
  await fireEvent.click(screen.getByRole("combobox", { name: "入职剧场" }));
  await fireEvent.click(await screen.findByText("西安幽州剧场", { selector: ".el-select-dropdown__item span" }));
  await fireEvent.click(await screen.findByRole("checkbox", { name: "西安幽州剧场：长离" }));
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));

  expect(await screen.findByRole("dialog", { name: "新增演员" })).toBeVisible();
  expect(await screen.findByText("角色能力保存失败")).toBeVisible();
  await fireEvent.click(screen.getByRole("button", { name: "保存演员" }));

  await waitFor(() => {
    expect(requests.filter((item) => item.method === "POST" && item.path === "/admin/actors")).toHaveLength(1);
    expect(requests.filter((item) => item.method === "PUT" && item.path === "/admin/actors/7/capabilities")).toHaveLength(2);
  });
});
