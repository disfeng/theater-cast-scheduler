import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import ElementPlus from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, test, vi } from "vitest";
import PerformanceBoardReview from "../src/components/admin/PerformanceBoardReview.vue";

beforeEach(() => { localStorage.clear(); localStorage.setItem("token", "admin-token"); localStorage.setItem("role", "admin"); vi.restoreAllMocks(); });
function mount(performanceId = 72) { const pinia = createPinia(); setActivePinia(pinia); return render(PerformanceBoardReview, { props: { performanceId }, global: { plugins: [pinia, ElementPlus] } }); }

test("当前场次信息板可逐条复核并激活", async () => {
  const requests: string[] = [];
  const revision: any = { id: 12, board_id: 8, revision_number: 2, raw_text: "原始证据", status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null, draft_items: [{ id: 101, revision_id: 12, item_kind: "wish", change_type: "added", raw_line: "许愿-小展/长离", player_name: "Jennifer", actor_id: 9, role_id: 5, note: null, validation_status: "valid", failure_reason: null, confirmed_at: null }] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, ""); const method = init?.method || "GET";
    if (path === "/admin/actors") return Response.json([{ id: 9, display_name: "小展", role_ids: [5] }]);
    if (path === "/admin/roles") return Response.json([{ id: 5, name: "长离" }]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 8, performance_id: 72, current_revision_id: null, revisions: [revision] });
    requests.push(`${method}:${path}`);
    if (path === "/admin/board-draft-items/101/confirm") { revision.draft_items[0].confirmed_at = "2026-07-17"; return Response.json(revision.draft_items[0]); }
    if (path === "/admin/board-revisions/12/activate") return Response.json({ ...revision, status: "confirmed", confirmed_at: "2026-07-17" });
    return Response.json({ detail: path }, { status: 500 });
  }));
  const mounted = mount();
  expect(await screen.findByText("许愿-小展/长离")).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button", { name: "确认此条" }));
  await waitFor(() => expect(requests).toContain("POST:/admin/board-draft-items/101/confirm"));
  expect(await screen.findByText("已确认")).toBeInTheDocument();
  const activateButton = screen.getByRole("button", { name: "激活当前版本" });
  await waitFor(() => expect(activateButton).toBeEnabled());
  await fireEvent.click(activateButton);
  await waitFor(() => expect(requests).toContain("POST:/admin/board-revisions/12/activate"));
  expect(await screen.findByText("版本 2 已激活")).toBeInTheDocument();
  expect(mounted.emitted().changed).toHaveLength(1);
});

test("历史版本可查看并回滚为新版本", async () => {
  const revisions: any[] = [
    { id: 20, board_id: 9, revision_number: 2, raw_text: "新版", status: "confirmed", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: "x", rollback_source_revision_id: null, draft_items: [{ id: 201, revision_id: 20, item_kind: "player", change_type: "modified", raw_line: "新版玩家", player_name: "新版玩家", validation_status: "valid", failure_reason: null, confirmed_at: "x" }] },
    { id: 19, board_id: 9, revision_number: 1, raw_text: "旧版", status: "confirmed", parser_type: "deterministic", created_at: "2026-07-16", confirmed_at: "x", rollback_source_revision_id: null, draft_items: [{ id: 191, revision_id: 19, item_kind: "player", change_type: "removed", raw_line: "旧版玩家", player_name: "旧版玩家", validation_status: "valid", failure_reason: null, confirmed_at: "x" }] },
  ];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => { const path = String(input).replace(/https?:\/\/localhost:\d+/, ""); if (path === "/admin/actors" || path === "/admin/roles") return Response.json([]); if (path === "/admin/performances/88/board") return Response.json({ id: 9, performance_id: 88, current_revision_id: 20, revisions }); if (path === "/admin/board-revisions/19/rollback") return Response.json({ ...revisions[1], id: 21, revision_number: 3, status: "review_required", rollback_source_revision_id: 19 }); return Response.json({ detail: path }, { status: 500 }); }));
  mount(88);
  expect(await screen.findByText(/新版玩家 ·/)).toBeInTheDocument();
  await fireEvent.click(screen.getAllByRole("button", { name: "查看" })[1]);
  expect(screen.getByText(/旧版玩家 ·/)).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button", { name: "回滚为新版本" }));
  expect(await screen.findByText("已创建回滚版本 3")).toBeInTheDocument();
});

test("智能解析失败后仍可仅保存原文草稿", async () => {
  const bodies: any[] = [];
  const created: any = { id: 30, board_id: 10, revision_number: 1, raw_text: "原始群信息", status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null, draft_items: [] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors" || path === "/admin/roles") return Response.json([]);
    if (path === "/admin/performances/72/board") return Response.json({ detail: "board_not_found" }, { status: 404 });
    if (path === "/admin/performances/72/board/revisions") {
      const body = JSON.parse(String(init?.body));
      bodies.push(body);
      if (body.parse_with_ai !== false) return Response.json({ detail: "provider_unavailable" }, { status: 503 });
      return Response.json(created);
    }
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();
  await fireEvent.update(await screen.findByLabelText("信息板原文"), "原始群信息");
  await fireEvent.click(screen.getByRole("button", { name: "解析为新版本" }));
  expect(await screen.findByText("provider_unavailable")).toBeInTheDocument();
  expect(screen.getByLabelText("信息板原文")).toHaveValue("原始群信息");
  await fireEvent.click(screen.getByRole("button", { name: "仅保存原文草稿" }));
  await waitFor(() => expect(bodies).toEqual([
    { raw_text: "原始群信息", parse_with_ai: true },
    { raw_text: "原始群信息", parse_with_ai: false },
  ]));
  expect(await screen.findByText("已保存原文草稿版本 1")).toBeInTheDocument();
});

test("已确认项默认折叠，待处理项显示原始匹配提示和中文错误", async () => {
  const revision: any = {
    id: 41, board_id: 14, revision_number: 2, raw_text: "群信息", status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null,
    draft_items: [
      { id: 401, revision_id: 41, item_kind: "player", change_type: "added", raw_line: "【昭昭】长离：Jennifer", player_name: "Jennifer", player_character_name: "昭昭", paired_role_name: "长离", validation_status: "valid", failure_reason: null, confirmed_at: "2026-07-17" },
      { id: 402, revision_id: 41, item_kind: "wish", change_type: "added", raw_line: "【虔诚许愿】-小展/长离-噜噜路", player_name: "噜噜路", actor_name_raw: "小展", role_name_raw: "长离", actor_id: null, role_id: null, validation_status: "invalid", failure_reason: "entity_matching_required", confirmed_at: null },
    ],
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors") return Response.json([{ id: 9, display_name: "小展", role_ids: [5] }]);
    if (path === "/admin/roles") return Response.json([{ id: 5, name: "长离" }]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 14, performance_id: 72, current_revision_id: null, revisions: [revision] });
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();
  expect(await screen.findByText("Jennifer · 昭昭 / 长离")).toBeInTheDocument();
  const playerRow = document.querySelector(".draft-row.kind-player");
  const wishRow = document.querySelector(".draft-row.kind-wish");
  expect(playerRow).toBeInTheDocument();
  expect(wishRow).toBeInTheDocument();
  expect(playerRow).toHaveTextContent("已确认");
  expect(playerRow).not.toHaveTextContent("有效");
  expect(playerRow?.querySelector(".kind-badge")).toHaveTextContent("玩家");
  expect(screen.queryByDisplayValue("Jennifer")).not.toBeInTheDocument();
  expect(screen.getByText("需要选择或确认匹配的演员、角色及玩家")).toBeInTheDocument();
  expect(screen.getByText("解析演员：小展")).toBeInTheDocument();
  expect(screen.getByText("解析角色：长离")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "演员（解析：小展）" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "角色（解析：长离）" })).toBeInTheDocument();
  await fireEvent.click(screen.getByRole("button", { name: "展开详情" }));
  expect(screen.getByDisplayValue("Jennifer")).toBeInTheDocument();
});

test("其他未解析项可手工改为许愿并在补全后确认", async () => {
  let submitted: any = null;
  const item: any = { id: 501, revision_id: 51, item_kind: "unresolved", change_type: "added", raw_line: "无法判断类型的登记", player_name: "微醺未醒", actor_name_raw: "小A", role_name_raw: "林月棠", actor_id: 9, role_id: 5, validation_status: "invalid", failure_reason: "unrecognized_line", confirmed_at: null };
  const revision: any = { id: 51, board_id: 15, revision_number: 1, raw_text: item.raw_line, status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null, draft_items: [item] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors") return Response.json([{ id: 9, display_name: "小A", role_ids: [5] }]);
    if (path === "/admin/roles") return Response.json([{ id: 5, name: "林月棠" }]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 15, performance_id: 72, current_revision_id: null, revisions: [revision] });
    if (path === "/admin/board-draft-items/501/confirm") {
      submitted = JSON.parse(String(init?.body));
      return Response.json({ ...item, ...submitted, validation_status: "valid", failure_reason: null, confirmed_at: "2026-07-17" });
    }
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();

  const confirm = await screen.findByRole("button", { name: "确认此条" });
  expect(confirm).toBeDisabled();
  await fireEvent.click(screen.getByRole("combobox", { name: "登记类型" }));
  await fireEvent.click(await screen.findByText("许愿登记"));
  expect(confirm).toBeEnabled();
  await fireEvent.click(confirm);

  await waitFor(() => expect(submitted).toMatchObject({ item_kind: "wish", player_name: "微醺未醒", actor_id: 9, role_id: 5 }));
  expect(await screen.findByText("已确认")).toBeInTheDocument();
});

test("虔诚许愿默认归类为许愿并从本版玩家下拉选择", async () => {
  let submitted: any = null;
  const revision: any = {
    id: 71, board_id: 17, revision_number: 1, raw_text: "群信息", status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null,
    draft_items: [
      { id: 701, revision_id: 71, item_kind: "player", change_type: "added", raw_line: "【顾辞烟】顾辞忧：Kiki", player_name: "Kiki", player_character_name: "顾辞烟", paired_role_name: "顾辞忧", validation_status: "valid", failure_reason: null, confirmed_at: "2026-07-17" },
      { id: 702, revision_id: 71, item_kind: "unresolved", change_type: "added", raw_line: "【虔诚许愿】 -仔仔/顾辞忧（kiki 没有仔仔kiki要哭死）", player_name: null, actor_id: 10, role_id: 6, validation_status: "invalid", failure_reason: "unrecognized_line", confirmed_at: null },
    ],
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors") return Response.json([{ id: 10, display_name: "仔仔", role_ids: [6] }]);
    if (path === "/admin/roles") return Response.json([{ id: 6, name: "顾辞忧" }]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 17, performance_id: 72, current_revision_id: null, revisions: [revision] });
    if (path === "/admin/board-draft-items/702/confirm") {
      submitted = JSON.parse(String(init?.body));
      return Response.json({ ...revision.draft_items[1], ...submitted, item_kind: "wish", confirmed_at: "2026-07-17" });
    }
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();

  expect(await screen.findByText("许愿")).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "登记类型" })).not.toBeInTheDocument();
  await fireEvent.click(screen.getByRole("combobox", { name: "许愿玩家" }));
  await fireEvent.click(await screen.findByRole("option", { name: "Kiki · 顾辞烟" }));
  await fireEvent.click(screen.getByRole("button", { name: "确认此条" }));
  await waitFor(() => expect(submitted).toMatchObject({ item_kind: "wish", player_name: "Kiki", actor_id: 10, role_id: 6 }));
});

test("确认接口错误通过全局 Message 显示中文提示", async () => {
  const item: any = { id: 601, revision_id: 61, item_kind: "wish", change_type: "added", raw_line: "许愿", player_name: "未登记玩家", actor_id: 9, role_id: 5, validation_status: "invalid", failure_reason: null, confirmed_at: null };
  const revision: any = { id: 61, board_id: 16, revision_number: 1, raw_text: "许愿", status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null, draft_items: [item] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors") return Response.json([{ id: 9, display_name: "小A", role_ids: [5] }]);
    if (path === "/admin/roles") return Response.json([{ id: 5, name: "林月棠" }]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 16, performance_id: 72, current_revision_id: null, revisions: [revision] });
    if (path === "/admin/board-draft-items/601/confirm") return Response.json({ detail: "player_claim_not_found" }, { status: 409 });
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();
  await fireEvent.click(await screen.findByRole("button", { name: "确认此条" }));
  const message = await screen.findByText("未找到对应玩家，请先确认同场玩家登记或修正玩家昵称");
  expect(message.closest(".el-message")).toBeInTheDocument();
  expect(document.querySelector(".board-review .el-alert")).not.toBeInTheDocument();
});

test("待复核版本的已确认项可重新编辑后再次确认", async () => {
  const requests: string[] = [];
  let submitted: any = null;
  const item: any = { id: 801, revision_id: 81, item_kind: "player", change_type: "added", raw_line: "【昭昭】长离：Jennifer-14-3", player_name: "Jennifer", player_character_name: "昭昭", paired_role_name: "长离", theater_visit_ordinal: 14, character_visit_ordinal: 3, validation_status: "valid", failure_reason: null, confirmed_at: "2026-07-17" };
  const revision: any = { id: 81, board_id: 18, revision_number: 1, raw_text: item.raw_line, status: "review_required", parser_type: "deterministic", created_at: "2026-07-17", confirmed_at: null, rollback_source_revision_id: null, draft_items: [item] };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/https?:\/\/localhost:\d+/, "");
    if (path === "/admin/actors" || path === "/admin/roles") return Response.json([]);
    if (path === "/admin/performances/72/board") return Response.json({ id: 18, performance_id: 72, current_revision_id: null, revisions: [revision] });
    requests.push(`${init?.method || "GET"}:${path}`);
    if (path === "/admin/board-draft-items/801/reopen") return Response.json({ ...item, confirmed_at: null });
    if (path === "/admin/board-draft-items/801/confirm") { submitted = JSON.parse(String(init?.body)); return Response.json({ ...item, ...submitted, confirmed_at: "2026-07-17" }); }
    return Response.json({ detail: path }, { status: 500 });
  }));
  mount();

  await fireEvent.click(await screen.findByRole("button", { name: "重新编辑" }));
  await waitFor(() => expect(requests).toContain("POST:/admin/board-draft-items/801/reopen"));
  await fireEvent.update(await screen.findByDisplayValue("Jennifer"), "Jennifer 修改");
  await fireEvent.update(screen.getByRole("spinbutton", { name: "刷剧场次数" }), "15");
  await fireEvent.update(screen.getByRole("spinbutton", { name: "刷角色次数" }), "4");
  await fireEvent.click(screen.getByRole("button", { name: "确认此条" }));
  await waitFor(() => expect(requests).toContain("POST:/admin/board-draft-items/801/confirm"));
  expect(submitted).toMatchObject({ theater_visit_ordinal: 15, character_visit_ordinal: 4 });
});
