import { render, screen } from "@testing-library/vue";
import ElementPlus from "element-plus";
import { expect, test, vi } from "vitest";
import SmsSettingsPanel from "../src/components/admin/SmsSettingsPanel.vue";

test("短信和剧场披露策略默认关闭且可测试", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path.includes("/system-settings/actor-notifications/logs")) return Response.json([]);
    if (path.includes("/system-settings/actor-notifications")) return Response.json({
      sms_enabled: false,
      actor_portal_url: "http://localhost:7003/actor",
      credentials_configured: false,
      access_key_id_masked: null,
      sign_name: null,
      template_code: null,
      endpoint: "dysmsapi.aliyuncs.com",
    });
    if (path.includes("/theaters/2/actor-notification-settings")) return Response.json({
      reveal_days_before: 1,
      reveal_time: "21:00:00",
      sms_enabled: false,
    });
    return Response.json({});
  }));
  render(SmsSettingsPanel, {
    props: { token: "token", theaterId: 2 },
    global: { plugins: [ElementPlus] },
  });
  expect(await screen.findByRole("switch", { name: "短信全局开关" })).not.toBeChecked();
  expect(screen.getByRole("spinbutton", { name: "提前天数" })).toHaveValue(1);
  expect(screen.getByRole("button", { name: "发送测试短信" })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "短信发送日志" })).toBeInTheDocument();
});
