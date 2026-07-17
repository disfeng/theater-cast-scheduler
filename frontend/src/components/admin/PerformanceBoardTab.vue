<template>
  <div class="board-workspace">
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert v-if="notice" :title="notice" type="success" show-icon :closable="false" />

    <div class="panel selection-panel">
      <h3>选择具体场次</h3>
      <div class="selector-grid">
        <label>选择剧场<select v-model="theaterId" aria-label="信息板选择剧场"><option value="">请选择</option><option v-for="theater in theaters" :key="theater.id" :value="String(theater.id)">{{ theater.name }}</option></select></label>
        <label>场次日期<input v-model="performanceDate" aria-label="场次日期" type="date" /></label>
        <label>选择场次<select v-model="performanceId" aria-label="选择场次" :disabled="loadingPerformances || !performanceDate"><option value="">{{ loadingPerformances ? "加载中…" : "请选择" }}</option><option v-for="performance in dayPerformances" :key="performance.id" :value="String(performance.id)">{{ performance.slot_name_snapshot }} · {{ performance.start_time_snapshot }}</option></select></label>
      </div>
      <p v-if="theaterId && performanceDate && !loadingPerformances && dayPerformances.length === 0" class="empty">当天没有可用场次。</p>
      <div v-if="selectedPerformance" class="performance-anchor">正在复核：{{ theaterName }} · {{ selectedPerformance.performance_date }} · {{ selectedPerformance.slot_name_snapshot }} {{ selectedPerformance.start_time_snapshot }} · 场次 ID：{{ selectedPerformance.id }}</div>
    </div>

    <template v-if="selectedPerformance">
      <div class="panel parse-panel">
        <h3>粘贴并解析信息板</h3>
        <label>信息板原文<textarea v-model="rawText" aria-label="信息板原文" rows="6" placeholder="粘贴玩家、指定与许愿原文" /></label>
        <el-button type="primary" :loading="creating" :disabled="creating || !rawText.trim()" @click="createRevision">解析为新版本</el-button>
      </div>

      <div v-if="loadingBoard" class="panel state">正在加载场次信息板…</div>
      <div v-else-if="!board && !revision" class="panel state">该场次尚无信息板版本，请粘贴原文创建。</div>
      <template v-else-if="revision">
        <div class="revision-head panel">
          <div><h3>版本 {{ revision.revision_number }} 复核</h3><p>场次 ID：{{ selectedPerformance.id }} · {{ statusLabel(revision.status) }}</p></div>
          <div class="actions">
            <el-button :loading="confirmingValid" :disabled="busy || revision.status !== 'review_required'" @click="confirmValid">确认全部有效项</el-button>
            <el-button type="success" :loading="activating" :disabled="busy || !allConfirmed || revision.status !== 'review_required'" @click="activate">激活版本 {{ revision.revision_number }}</el-button>
          </div>
        </div>
        <p v-if="isHistory" class="diff-caption">与当前激活版本 {{ currentRevision?.revision_number }} 对比；以下颜色表示该历史版本记录的 diff。</p>
        <div v-if="revision.draft_items.length === 0" class="panel state">此版本没有解析条目。</div>
        <article v-for="item in revision.draft_items" :key="item.id" :data-testid="`board-item-${item.id}`" class="board-item" :class="`change-${item.change_type}`">
          <header><strong>{{ kindLabel(item.item_kind) }}</strong><el-tag size="small" :type="changeTag(item.change_type)">{{ changeLabel(item.change_type) }}</el-tag><el-tag size="small" :type="validationTag(item.validation_status)">{{ validationLabel(item.validation_status) }}</el-tag><span v-if="item.confirmed_at" class="confirmed">已确认</span></header>
          <div class="evidence"><span>原始证据</span><code>{{ item.raw_line || "（无原文）" }}</code></div>
          <p v-if="item.item_kind === 'wish' && item.performance_player_id" class="wish-link">已关联本场玩家 #{{ item.performance_player_id }}<template v-if="item.wish_id"> · 许愿 #{{ item.wish_id }}</template></p>
          <div v-if="item.confidence && Object.keys(item.confidence).length" class="confidence">字段置信度：<span v-for="(value, field) in item.confidence" :key="field">{{ field }} {{ Math.round(value * 100) }}% </span></div>
          <div class="correction-grid">
            <label>玩家<input v-model="item.player_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">角色名<input v-model="item.player_character_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind === 'player'">配对角色<input v-model="item.paired_role_name" :disabled="!!item.confirmed_at || isHistory" /></label>
            <label v-if="item.item_kind !== 'player'">演员<select v-model="item.actor_id" :disabled="!!item.confirmed_at || isHistory"><option :value="null">未选择</option><option v-for="actor in actors" :key="actor.id" :value="actor.id">{{ actor.display_name }}</option></select></label>
            <label v-if="item.item_kind !== 'player'">角色<select v-model="item.role_id" :disabled="!!item.confirmed_at || isHistory"><option :value="null">未选择</option><option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option></select></label>
          </div>
          <fieldset v-if="item.candidates?.length && !item.confirmed_at && !isHistory"><legend>歧义候选（必须显式选择）</legend><label v-for="candidate in item.candidates" :key="`${candidate.field}-${candidate.id}`"><input type="radio" :name="`candidate-${item.id}-${candidate.field}`" :aria-label="`候选 ${candidate.label}`" @click="selectCandidate(item, candidate.field, candidate.id)" />{{ candidate.label }}</label></fieldset>
          <label v-if="item.change_type === 'removed' && !item.confirmed_at && !isHistory" class="lifecycle"><input v-model="item.removal_lifecycle_confirmed" type="checkbox" aria-label="确认移除并结束生命周期" />确认移除并结束生命周期</label>
          <p v-if="item.failure_reason" class="failure">{{ item.failure_reason }}</p>
          <el-button v-if="!isHistory && !item.confirmed_at" size="small" :loading="busyItemId === item.id" :disabled="busy || item.item_kind === 'unresolved' || (item.validation_status === 'ambiguous' && !resolvedItems.has(item.id)) || (item.change_type === 'removed' && !item.removal_lifecycle_confirmed)" @click="confirmItem(item)">确认此条</el-button>
        </article>
      </template>

      <div v-if="board?.revisions.length" class="panel history">
        <h3>版本历史</h3>
        <div v-for="entry in sortedRevisions" :key="entry.id" class="history-row"><span>版本 {{ entry.revision_number }} · {{ statusLabel(entry.status) }}<em v-if="board.current_revision_id === entry.id">当前激活</em></span><div><el-button size="small" @click="revision = entry">查看版本 {{ entry.revision_number }}</el-button><el-button v-if="entry.status === 'confirmed' && board.current_revision_id !== entry.id" size="small" :loading="rollingBackId === entry.id" :disabled="busy" @click="rollback(entry)">回滚版本 {{ entry.revision_number }} 为新版本</el-button></div></div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { adminApi } from "../../api/admin";
import type { Actor, Performance, Role, Theater } from "../../api/admin";
import type { BoardCandidate, BoardDraftItem, BoardRevision, PerformanceBoard } from "../../features/performance-board/types";
import { useAuthStore } from "../../auth/store";

const auth = useAuthStore();
const route = useRoute(); const router = useRouter();
const theaters = ref<Theater[]>([]); const actors = ref<Actor[]>([]); const roles = ref<Role[]>([]); const performances = ref<Performance[]>([]);
const theaterId = ref(String(route.query.theater_id ?? "")); const performanceDate = ref(String(route.query.performance_date ?? "")); const performanceId = ref(String(route.query.performance_id ?? "")); const rawText = ref("");
const board = ref<PerformanceBoard | null>(null); const revision = ref<BoardRevision | null>(null); const error = ref(""); const notice = ref("");
const loadingPerformances = ref(false); const loadingBoard = ref(false); const creating = ref(false); const confirmingValid = ref(false); const activating = ref(false); const rollingBackId = ref<number | null>(null); const busyItemId = ref<number | null>(null); const resolvedItems = ref(new Set<number>());
const candidateSelections = ref(new Map<number, { field: string; id: number }>());
const busy = computed(() => creating.value || confirmingValid.value || activating.value || rollingBackId.value !== null || busyItemId.value !== null);
const dayPerformances = computed(() => performances.value.filter(p => p.performance_date === performanceDate.value));
const selectedPerformance = computed(() => performances.value.find(p => p.id === Number(performanceId.value)) ?? null);
const theaterName = computed(() => theaters.value.find(t => t.id === Number(theaterId.value))?.name ?? "未知剧场");
const currentRevision = computed(() => board.value?.revisions.find(r => r.id === board.value?.current_revision_id) ?? null);
const isHistory = computed(() => !!revision.value && !!board.value?.current_revision_id && revision.value.id !== board.value.current_revision_id);
const allConfirmed = computed(() => !!revision.value?.draft_items.length && revision.value.draft_items.every(item => !!item.confirmed_at));
const sortedRevisions = computed(() => [...(board.value?.revisions ?? [])].sort((a, b) => b.revision_number - a.revision_number));

let performanceRequest = 0; let performanceAbort: AbortController | null = null; let boardRequest = 0; let boardAbort: AbortController | null = null;
onMounted(async () => { if (!auth.token) return; try { [theaters.value, actors.value, roles.value] = await Promise.all([adminApi.getTheaters(auth.token), adminApi.getActors(auth.token), adminApi.getRoles(auth.token)]); } catch (e: any) { error.value = e.message; } });
watch([theaterId, performanceDate], async ([theater, date], [oldTheater, oldDate]) => {
  const restoring = !!route.query.performance_id && theater === String(route.query.theater_id) && date === String(route.query.performance_date);
  if (!restoring && (theater !== oldTheater || date !== oldDate)) performanceId.value = "";
  performances.value = []; board.value = null; revision.value = null; performanceAbort?.abort(); const token = ++performanceRequest;
  if (!auth.token || !theater || !date) return;
  const controller = new AbortController(); performanceAbort = controller; loadingPerformances.value = true; error.value = "";
  try { const [year, month] = date.split("-").map(Number); const result = await adminApi.getPerformances(auth.token, Number(theater), year, month, controller.signal); if (token === performanceRequest) performances.value = result; }
  catch (e: any) { if (token === performanceRequest && e.name !== "AbortError") error.value = e.message; }
  finally { if (token === performanceRequest) loadingPerformances.value = false; }
}, { immediate: true });
watch(performanceId, async value => {
  boardAbort?.abort(); const token = ++boardRequest; board.value = null; revision.value = null;
  if (!auth.token || !value) { persistQuery(); return; }
  const controller = new AbortController(); boardAbort = controller; loadingBoard.value = true; error.value = ""; persistQuery();
  try { const result = await adminApi.getPerformanceBoard(auth.token, Number(value), controller.signal); if (token !== boardRequest) return; board.value = result; const requested = Number(route.query.revision_id); revision.value = result.revisions.find(r => r.id === requested) ?? currentRevision.value ?? sortedRevisions.value[0] ?? null; }
  catch (e: any) { if (token === boardRequest && e.name !== "AbortError" && e.status !== 404) error.value = e.message; }
  finally { if (token === boardRequest) loadingBoard.value = false; }
}, { immediate: true });
watch(revision, value => { if (value && performanceId.value) persistQuery(value.id); });
function persistQuery(revisionId?: number) { router.replace({ query: { ...route.query, theater_id: theaterId.value || undefined, performance_date: performanceDate.value || undefined, performance_id: performanceId.value || undefined, revision_id: revisionId ?? route.query.revision_id ?? undefined } }); }

async function createRevision() { if (!auth.token || !selectedPerformance.value || creating.value) return; creating.value = true; error.value = ""; notice.value = ""; try { const created = await adminApi.createBoardRevision(auth.token, selectedPerformance.value.id, rawText.value); revision.value = created; board.value = board.value ? { ...board.value, revisions: [created, ...board.value.revisions] } : { id: created.board_id, performance_id: selectedPerformance.value.id, current_revision_id: null, revisions: [created] }; notice.value = `已创建版本 ${created.revision_number}，请逐项复核。`; } catch (e: any) { error.value = e.message; } finally { creating.value = false; } }
function selectCandidate(item: BoardDraftItem, field: string, id: number) { candidateSelections.value = new Map(candidateSelections.value).set(item.id, { field, id }); resolvedItems.value = new Set(resolvedItems.value).add(item.id); }
function itemPatch(item: BoardDraftItem) { const patch: any = { player_name: item.player_name, player_character_name: item.player_character_name, paired_role_name: item.paired_role_name, matched_player_id: item.matched_player_id, actor_id: item.actor_id, role_id: item.role_id, note: item.note, removal_lifecycle_confirmed: item.removal_lifecycle_confirmed }; const selected = candidateSelections.value.get(item.id); if (selected) patch[selected.field] = selected.id; return patch; }
async function confirmItem(item: BoardDraftItem) { if (!auth.token || busy.value) return; busyItemId.value = item.id; error.value = ""; try { Object.assign(item, await adminApi.confirmBoardDraftItem(auth.token, item.id, itemPatch(item))); } catch (e: any) { error.value = e.message; } finally { busyItemId.value = null; } }
async function confirmValid() { if (!auth.token || !revision.value || busy.value) return; confirmingValid.value = true; try { revision.value = await adminApi.confirmValidBoardItems(auth.token, revision.value.id); syncRevision(); } catch (e: any) { error.value = e.message; } finally { confirmingValid.value = false; } }
async function activate() { if (!auth.token || !revision.value || busy.value) return; activating.value = true; try { revision.value = await adminApi.activateBoardRevision(auth.token, revision.value.id); if (board.value) board.value.current_revision_id = revision.value.id; syncRevision(); notice.value = `版本 ${revision.value.revision_number} 已激活`; } catch (e: any) { error.value = e.message; } finally { activating.value = false; } }
async function rollback(entry: BoardRevision) { if (!auth.token || busy.value) return; rollingBackId.value = entry.id; try { const clone = await adminApi.rollbackBoardRevision(auth.token, entry.id); revision.value = clone; board.value?.revisions.unshift(clone); notice.value = `已创建回滚草稿版本 ${clone.revision_number}`; } catch (e: any) { error.value = e.message; } finally { rollingBackId.value = null; } }
function syncRevision() { if (!board.value || !revision.value) return; const index = board.value.revisions.findIndex(r => r.id === revision.value!.id); if (index >= 0) board.value.revisions[index] = revision.value; }
const kindLabel = (v: string) => ({ player: "玩家", designation: "指定", wish: "许愿", unresolved: "未解析" }[v] ?? v);
const changeLabel = (v: string) => ({ added: "新增", modified: "修改", removed: "移除", unchanged: "未变化" }[v] ?? v);
const validationLabel = (v: string) => ({ valid: "有效", ambiguous: "有歧义", invalid: "无效" }[v] ?? v);
const statusLabel = (v: string) => ({ review_required: "待复核", confirmed: "已激活", failed: "失败" }[v] ?? v);
const changeTag = (v: string): any => ({ added: "success", modified: "warning", removed: "danger", unchanged: "info" }[v] ?? "info");
const validationTag = (v: string): any => ({ valid: "success", ambiguous: "warning", invalid: "danger" }[v] ?? "info");
</script>

<style scoped>
.board-workspace{display:grid;gap:20px}.selection-panel h3,.parse-panel h3,.revision-head h3,.history h3{margin-top:0}.selector-grid,.correction-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}label{display:grid;gap:6px;font-size:14px}input,select,textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--panel-border);border-radius:7px;background:rgba(255,255,255,.05);color:var(--text-primary)}textarea{resize:vertical}.performance-anchor{margin-top:16px;padding:12px;border-left:4px solid var(--primary);background:rgba(99,102,241,.08);font-weight:600}.parse-panel{display:grid;gap:14px}.parse-panel .el-button{justify-self:end}.state,.empty{color:var(--text-secondary)}.revision-head,.history-row{display:flex;justify-content:space-between;align-items:center;gap:12px}.revision-head p{margin-bottom:0;color:var(--text-secondary)}.actions{display:flex;flex-wrap:wrap;gap:8px}.board-item{display:grid;gap:12px;padding:16px;border:1px solid var(--panel-border);border-left-width:5px;border-radius:9px;background:var(--panel-bg)}.board-item header{display:flex;align-items:center;gap:8px}.change-added{border-left-color:#22c55e}.change-modified{border-left-color:#f59e0b}.change-removed{border-left-color:#ef4444}.change-unchanged{border-left-color:#94a3b8}.confirmed{margin-left:auto;color:#22c55e}.evidence{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:start}.evidence span,.confidence{color:var(--text-secondary);font-size:13px}.evidence code{white-space:pre-wrap;word-break:break-word}.failure{color:#ef4444;margin:0}fieldset{display:flex;flex-wrap:wrap;gap:12px;border:1px dashed #f59e0b;border-radius:7px}fieldset label,.lifecycle{display:flex;align-items:center;gap:6px}fieldset input,.lifecycle input{width:auto}.history{display:grid;gap:10px}.history-row{padding-top:10px;border-top:1px solid var(--panel-border)}.history-row em{margin-left:8px;color:#22c55e;font-style:normal}.diff-caption{padding:10px;border-radius:7px;background:rgba(99,102,241,.08)}@media(max-width:760px){.selector-grid,.correction-grid{grid-template-columns:1fr}.revision-head,.history-row{align-items:stretch;flex-direction:column}.actions{width:100%}.actions .el-button{flex:1}.evidence{grid-template-columns:1fr}}
</style>
