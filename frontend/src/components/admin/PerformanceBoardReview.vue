<template>
  <section class="board-review">
    <div class="composer">
      <el-input v-model="rawText" type="textarea" :rows="5" aria-label="信息板原文" placeholder="粘贴本场玩家、指定与许愿原文" />
      <div class="composer-actions">
        <el-button :loading="creatingMode === 'draft'" :disabled="!rawText.trim() || busy" @click="createRevision(false)">仅保存原文草稿</el-button>
        <el-button type="primary" :loading="creatingMode === 'ai'" :disabled="!rawText.trim() || busy" @click="createRevision(true)">解析为新版本</el-button>
      </div>
    </div>

    <div v-if="loading" class="state">正在加载场次信息板…</div>
    <el-empty v-else-if="!revision" description="该场次尚无信息板版本" :image-size="72" />
    <template v-else>
      <header class="revision-head">
        <div><strong>版本 {{ revision.revision_number }}</strong><span>{{ statusLabel(revision.status) }}</span></div>
        <div>
          <el-button :loading="confirming" :disabled="busy || revision.status !== 'review_required'" @click="confirmValid">确认全部有效项</el-button>
          <el-button type="success" :loading="activating" :disabled="busy || !allConfirmed || revision.status !== 'review_required'" @click="activate">激活当前版本</el-button>
        </div>
      </header>

      <el-empty v-if="!revision.draft_items.length" description="此版本没有解析条目" :image-size="64" />
      <article v-for="item in revision.draft_items" :key="item.id" class="draft-row" :class="[`kind-${item.item_kind}`, { compact: item.confirmed_at && !expandedConfirmed.has(item.id) }]">
        <header>
          <div class="row-identity"><span class="kind-badge">{{ kindLabel(item.item_kind) }}</span><span v-if="item.confirmed_at" class="summary">{{ itemSummary(item) }}</span></div>
          <div class="row-status">
            <el-tag class="change-tag" size="small" effect="plain">{{ changeLabel(item.change_type) }}</el-tag>
            <el-tag v-if="!item.confirmed_at" size="small" effect="light" :type="validationTag(item.validation_status)">{{ validationLabel(item.validation_status) }}</el-tag>
            <span v-if="item.confirmed_at" class="confirmed"><span aria-hidden="true">✓</span> 已确认</span>
            <el-button v-if="item.confirmed_at && revision.status === 'review_required' && !isHistory" class="secondary-action" text size="small" :loading="busyItemId === item.id" @click="reopenItem(item)">重新编辑</el-button>
            <el-button v-if="item.confirmed_at" class="detail-action" text size="small" @click="toggleConfirmed(item.id)">{{ expandedConfirmed.has(item.id) ? "收起详情" : "展开详情" }}</el-button>
          </div>
        </header>
        <template v-if="!item.confirmed_at || expandedConfirmed.has(item.id)">
          <code>{{ item.raw_line || evidenceFallback(item) }}</code>
          <div v-if="item.item_kind !== 'player' && (item.actor_name_raw || item.role_name_raw)" class="parse-hints">
            <span v-if="item.actor_name_raw">解析演员：{{ item.actor_name_raw }}</span>
            <span v-if="item.role_name_raw">解析角色：{{ item.role_name_raw }}</span>
          </div>
          <div class="fields" :class="{ 'fields-three': item.item_kind !== 'unresolved' }">
            <label v-if="item.item_kind === 'unresolved'">登记类型<el-select v-model="item.item_kind" aria-label="登记类型" placeholder="请选择登记类型"><el-option label="玩家登记" value="player" /><el-option label="指定登记" value="designation" /><el-option label="许愿登记" value="wish" /></el-select></label>
            <label>玩家<el-select v-if="item.item_kind === 'wish'" v-model="item.player_name" aria-label="许愿玩家" placeholder="请选择本场玩家" :disabled="!!item.confirmed_at || isHistory"><el-option v-for="player in playerOptions" :key="player.value" :label="player.label" :value="player.value" /></el-select><el-input v-else v-model="item.player_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">玩家角色<el-input v-model="item.player_character_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">对位角色<el-input v-model="item.paired_role_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">刷剧场次数<el-input-number v-model="item.theater_visit_ordinal" :min="1" :controls="false" placeholder="未登记" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">刷角色次数<el-input-number v-model="item.character_visit_ordinal" :min="1" :controls="false" placeholder="未登记" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind !== 'player'">演员<el-select v-model="item.actor_id" :aria-label="`演员${item.actor_name_raw ? `（解析：${item.actor_name_raw}）` : ''}`" placeholder="请选择演员" :disabled="!!item.confirmed_at || isHistory" clearable><el-option v-for="actor in availableActors(item)" :key="actor.id" :label="actor.display_name" :value="actor.id" /></el-select></label>
            <label v-if="item.item_kind !== 'player'">角色<el-select v-model="item.role_id" :aria-label="`角色${item.role_name_raw ? `（解析：${item.role_name_raw}）` : ''}`" placeholder="请选择角色" :disabled="!!item.confirmed_at || isHistory" clearable><el-option v-for="role in availableRoles(item)" :key="role.id" :label="role.name" :value="role.id" /></el-select></label>
          </div>
          <p v-if="item.failure_reason && !item.confirmed_at" class="failure">{{ failureLabel(item) }}</p>
          <el-button v-if="!item.confirmed_at && !isHistory" class="confirm-action" size="small" :loading="busyItemId === item.id" :disabled="busy || !canConfirm(item)" @click="confirmItem(item)">确认此条</el-button>
        </template>
      </article>

      <section v-if="board?.revisions.length" class="history">
        <h4>版本历史</h4>
        <div v-for="entry in sortedRevisions" :key="entry.id">
          <span>版本 {{ entry.revision_number }} · {{ statusLabel(entry.status) }}</span>
          <div><el-button size="small" @click="revision = entry">查看</el-button><el-button v-if="entry.status === 'confirmed' && board.current_revision_id !== entry.id" size="small" :disabled="busy" @click="rollback(entry)">回滚为新版本</el-button></div>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { adminApi, type Actor, type Role } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { BoardDraftItem, BoardRevision, PerformanceBoard } from "../../features/performance-board/types";

const props = defineProps<{ performanceId: number }>();
const emit = defineEmits<{ changed: [] }>();
const auth = useAuthStore();
const board = ref<PerformanceBoard | null>(null);
const revision = ref<BoardRevision | null>(null);
const actors = ref<Actor[]>([]);
const roles = ref<Role[]>([]);
const rawText = ref("");
const loading = ref(false);
const creatingMode = ref<"ai" | "draft" | null>(null);
const confirming = ref(false);
const activating = ref(false);
const busyItemId = ref<number | null>(null);
const expandedConfirmed = ref(new Set<number>());
const busy = computed(() => creatingMode.value !== null || confirming.value || activating.value || busyItemId.value !== null);
const sortedRevisions = computed(() => [...(board.value?.revisions || [])].sort((a, b) => b.revision_number - a.revision_number));
const playerOptions = computed(() => { const seen = new Set<string>(); return (revision.value?.draft_items || []).filter(item => item.item_kind === "player" && item.change_type !== "removed" && item.player_name?.trim()).flatMap(item => { const value = item.player_name!.trim(); const key = value.toLocaleLowerCase(); if (seen.has(key)) return []; seen.add(key); return [{ value, label: `${value} · ${item.player_character_name || "未登记角色"}` }]; }); });
const allConfirmed = computed(() => !!revision.value?.draft_items.length && revision.value.draft_items.every(item => !!item.confirmed_at));
const isHistory = computed(() => !!revision.value && !!board.value?.current_revision_id && revision.value.id !== board.value.current_revision_id);

onMounted(async () => {
  if (!auth.token) return;
  const [actorResult, roleResult] = await Promise.allSettled([adminApi.getActors(auth.token), adminApi.getRoles(auth.token)]);
  if (actorResult.status === "fulfilled") actors.value = actorResult.value;
  if (roleResult.status === "fulfilled") roles.value = roleResult.value;
});
watch(() => props.performanceId, loadBoard, { immediate: true });

async function loadBoard() {
  if (!auth.token || !props.performanceId) return;
  loading.value = true;
  try {
    board.value = await adminApi.getPerformanceBoard(auth.token, props.performanceId);
    revision.value = prepareRevision(board.value.revisions.find(item => item.id === board.value?.current_revision_id) || sortedRevisions.value[0] || null);
  } catch (cause: any) {
    if (cause.status === 404) { board.value = null; revision.value = null; }
    else showError(cause.message || "加载信息板失败");
  } finally { loading.value = false; }
}

async function createRevision(parseWithAi: boolean) {
  if (!auth.token || !rawText.value.trim()) return;
  creatingMode.value = parseWithAi ? "ai" : "draft";
  try {
    const created = await adminApi.createBoardRevision(auth.token, props.performanceId, rawText.value.trim(), parseWithAi);
    board.value = board.value ? { ...board.value, revisions: [created, ...board.value.revisions] } : { id: created.board_id, performance_id: props.performanceId, current_revision_id: null, revisions: [created] };
    revision.value = prepareRevision(created); rawText.value = ""; ElMessage.success(parseWithAi ? `已创建版本 ${created.revision_number}，请复核。` : `已保存原文草稿版本 ${created.revision_number}`);
  } catch (cause: any) { showError(cause.message || "解析信息板失败"); }
  finally { creatingMode.value = null; }
}

async function confirmItem(item: BoardDraftItem) {
  if (!auth.token) return;
  busyItemId.value = item.id;
  try {
    Object.assign(item, await adminApi.confirmBoardDraftItem(auth.token, item.id, { item_kind: item.item_kind === "unresolved" ? null : item.item_kind, player_name: item.player_name, player_character_name: item.player_character_name, paired_role_name: item.paired_role_name, theater_visit_ordinal: item.theater_visit_ordinal, character_visit_ordinal: item.character_visit_ordinal, actor_id: item.actor_id, role_id: item.role_id, note: item.note }));
    if (item.item_kind === "designation") emit("changed");
  }
  catch (cause: any) { showError(operationErrorLabel(cause.message) || "确认条目失败"); }
  finally { busyItemId.value = null; }
}
async function reopenItem(item: BoardDraftItem) {
  if (!auth.token) return;
  busyItemId.value = item.id;
  try { Object.assign(item, await adminApi.reopenBoardDraftItem(auth.token, item.id)); const next = new Set(expandedConfirmed.value); next.add(item.id); expandedConfirmed.value = next; }
  catch (cause: any) { showError(operationErrorLabel(cause.message) || "重新编辑失败"); }
  finally { busyItemId.value = null; }
}
async function confirmValid() { if (!auth.token || !revision.value) return; confirming.value = true; try { revision.value = await adminApi.confirmValidBoardItems(auth.token, revision.value.id); syncRevision(); } catch (cause: any) { showError(cause.message); } finally { confirming.value = false; } }
async function activate() { if (!auth.token || !revision.value) return; activating.value = true; try { revision.value = await adminApi.activateBoardRevision(auth.token, revision.value.id); if (board.value) board.value.current_revision_id = revision.value.id; syncRevision(); ElMessage.success(`版本 ${revision.value.revision_number} 已激活`); emit("changed"); } catch (cause: any) { showError(cause.message); } finally { activating.value = false; } }
async function rollback(entry: BoardRevision) { if (!auth.token) return; try { const created = await adminApi.rollbackBoardRevision(auth.token, entry.id); board.value?.revisions.unshift(created); revision.value = created; ElMessage.success(`已创建回滚版本 ${created.revision_number}`); emit("changed"); } catch (cause: any) { showError(cause.message); } }
function syncRevision() { if (!board.value || !revision.value) return; const index = board.value.revisions.findIndex(item => item.id === revision.value?.id); if (index >= 0) board.value.revisions[index] = revision.value; }
function prepareRevision(value: BoardRevision | null) { if (!value) return null; for (const item of value.draft_items) { if (item.item_kind === "unresolved" && item.raw_line?.includes("【虔诚许愿】")) item.item_kind = "wish"; } return value; }
const kindLabel = (value: string) => ({ player: "玩家", designation: "指定", wish: "许愿", unresolved: "未解析" }[value] || value);
const changeLabel = (value: string) => ({ added: "新增", modified: "修改", removed: "移除", unchanged: "未变" }[value] || value);
const validationLabel = (value: string) => ({ valid: "有效", ambiguous: "有歧义", invalid: "无效" }[value] || value);
const validationTag = (value: string): "success" | "warning" | "danger" | "info" => ({ valid: "success", ambiguous: "warning", invalid: "danger" }[value] as any || "info");
const statusLabel = (value: string) => ({ review_required: "待复核", confirmed: "已激活", failed: "失败" }[value] || value);
function failureLabel(item: BoardDraftItem) {
  if (item.failure_reason === "entity_matching_required") return item.item_kind === "designation" ? "需要选择或确认匹配的演员及角色" : "需要选择或确认匹配的演员、角色及玩家";
  const value = item.failure_reason || "";
  return ({ player_identity_required: "需要补充并确认玩家身份", player_match_ambiguous: "匹配到多个玩家，请明确选择", actor_role_capability_missing: "该演员未配置此角色的出演能力", role_out_of_performance_scope: "角色不属于当前剧场", unrecognized_line: "未能识别此行内容", duplicate_stable_key: "存在重复登记，请核对" }[value] || `需要人工复核（${value}）`);
}
const operationErrorLabel = (value: string) => ({ player_claim_not_found: "未找到对应玩家，请先确认同场玩家登记或修正玩家昵称", player_match_ambiguous: "同场存在多个同名玩家，请先明确玩家身份", player_candidate_invalid: "所选玩家与登记昵称不一致" }[value] || value);
function showError(message?: string) { ElMessage.error(message || "操作失败，请稍后重试"); }
function toggleConfirmed(id: number) { const next = new Set(expandedConfirmed.value); next.has(id) ? next.delete(id) : next.add(id); expandedConfirmed.value = next; }
function itemSummary(item: BoardDraftItem) { if (item.item_kind === "player") return `${item.player_name || "未登记玩家"} · ${item.player_character_name || "未识别角色"} / ${item.paired_role_name || "未识别对位"}`; const actor = actors.value.find(row => row.id === item.actor_id)?.display_name || item.actor_name_raw || "未匹配演员"; const role = roles.value.find(row => row.id === item.role_id)?.name || item.role_name_raw || "未匹配角色"; return `${item.player_name || "未登记玩家"} · ${actor} / ${role}`; }
function evidenceFallback(item: BoardDraftItem) { const parts = [item.actor_name_raw, item.role_name_raw, item.player_name].filter(Boolean); return parts.length ? `解析内容：${parts.join(" / ")}` : "（未保留原始证据）"; }
function availableActors(item: BoardDraftItem) { return item.role_id ? actors.value.filter(actor => actor.role_ids?.includes(item.role_id!)) : actors.value; }
function availableRoles(item: BoardDraftItem) { const actor = actors.value.find(row => row.id === item.actor_id); return actor ? roles.value.filter(role => actor.role_ids?.includes(role.id)) : roles.value; }
function canConfirm(item: BoardDraftItem) { if (item.item_kind === "unresolved") return false; if (!item.player_name?.trim()) return false; if (item.item_kind === "player" && (!item.player_character_name?.trim() || !item.paired_role_name?.trim())) return false; if (item.item_kind !== "player" && (!item.actor_id || !item.role_id)) return false; return true; }
</script>

<style scoped>
.board-review,.composer{display:grid;gap:14px}.composer-actions{display:flex;justify-content:flex-end;gap:10px}.state{padding:24px;text-align:center;color:#748096}.revision-head,.revision-head>div,.draft-row header,.history>div{display:flex;align-items:center;justify-content:space-between;gap:10px}.revision-head{padding:12px 0;border-bottom:1px solid #e5e9f0}.revision-head span{margin-left:10px;color:#748096}.draft-row{--kind-color:#94a3b8;--kind-soft:#f1f5f9;--kind-text:#475569;display:grid;gap:10px;padding:14px 16px;border:1px solid #e1e6ef;border-left:5px solid var(--kind-color);border-radius:12px;background:#fff}.draft-row.kind-player{--kind-color:#3b82f6;--kind-soft:#eff6ff;--kind-text:#2563eb}.draft-row.kind-designation{--kind-color:#8b5cf6;--kind-soft:#f5f3ff;--kind-text:#7c3aed}.draft-row.kind-wish{--kind-color:#f59e0b;--kind-soft:#fffbeb;--kind-text:#b45309}.draft-row.kind-unresolved{--kind-color:#ef4444;--kind-soft:#fef2f2;--kind-text:#dc2626}.draft-row.compact{gap:0;padding-block:10px}.row-identity,.row-status,.parse-hints{display:flex;align-items:center;gap:9px}.row-identity{min-width:0}.kind-badge{flex:0 0 auto;padding:4px 10px;border-radius:999px;background:var(--kind-soft);color:var(--kind-text);font-size:14px;font-weight:700}.summary{overflow:hidden;color:#536078;text-overflow:ellipsis;white-space:nowrap}.row-status{flex-shrink:0;gap:8px}.change-tag{border-color:#dbe3ee!important;background:#f8fafc!important;color:#64748b!important}.confirmed{display:inline-flex;align-items:center;gap:4px;color:#16865b;font-size:14px;font-weight:600}.secondary-action,.detail-action{margin-left:0!important}.secondary-action{color:#64748b}.detail-action{color:#334155;font-weight:600}.draft-row code{padding:8px 10px;border-radius:7px;background:#f7f9fc;white-space:pre-wrap;color:#536078}.parse-hints{color:#64748b;font-size:13px}.parse-hints span{padding:3px 8px;border-radius:999px;background:#f0f4fa}.fields{display:grid;grid-template-columns:minmax(110px,.7fr) repeat(3,minmax(140px,1fr));gap:10px}.fields.fields-three{grid-template-columns:repeat(3,minmax(0,1fr))}.fields label{display:grid;gap:5px;color:#64748b;font-size:13px}.fields .el-input-number{width:100%}.failure{margin:0;color:#d84f4f;font-size:13px}.confirm-action{justify-self:end;min-width:96px}.history{display:grid;gap:8px;padding-top:8px}.history>div{padding:9px 0;border-top:1px solid #e5e9f0}@media(max-width:720px){.fields,.fields.fields-three{grid-template-columns:1fr 1fr}.revision-head,.draft-row header{align-items:flex-start;flex-direction:column}.row-status{width:100%;flex-wrap:wrap}.composer-actions{flex-direction:column-reverse}.composer-actions .el-button{width:100%;margin-left:0}}@media(max-width:480px){.fields,.fields.fields-three{grid-template-columns:1fr}}
</style>
