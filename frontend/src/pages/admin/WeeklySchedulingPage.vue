<template>
  <section class="scheduling-page">
    <PageHeader title="周排班" description="按月度计划为每场演出的每个角色安排演员，支持推荐、冲突复核与发布。" />
    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />

    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="field"><span>剧场</span><el-select v-model="theaterId" style="width: 210px" @change="loadWorkspace"><el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="week-nav">
          <el-button aria-label="上一周" circle @click="changeWeek(-1)"><el-icon><ArrowLeft /></el-icon></el-button>
          <div><small>当前排班周</small><strong>{{ workspace ? weekLabel(workspace.week_start, workspace.week_end) : weekLabel(weekStart, weekEnd) }}</strong></div>
          <el-button aria-label="下一周" circle @click="changeWeek(1)"><el-icon><ArrowRight /></el-icon></el-button>
        </div>
        <div class="status-block">
          <el-tag :type="statusType">{{ statusText }}</el-tag>
          <span>{{ assignedCount }}/{{ totalCells }} 已安排</span>
          <span v-if="workspace?.conflicts.length" class="danger">{{ workspace.conflicts.length }} 个冲突</span>
          <span v-if="workspace?.warnings.length" class="warning">{{ workspace.warnings.length }} 个提醒</span>
        </div>
        <div class="actions">
          <el-button :loading="recommending" :disabled="!workspace?.performances.length" @click="recommend">推荐排班</el-button>
          <el-button :loading="validating" :disabled="!workspace" @click="validate">冲突检测</el-button>
          <el-button :loading="saving" :disabled="!workspace" @click="persist(false)">保存草稿</el-button>
          <el-button type="primary" :loading="publishing" :disabled="!workspace" @click="persist(true)">发布排班</el-button>
        </div>
      </div>
    </el-card>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-empty v-else-if="!theaters.length" description="请先新增剧场" />
    <el-empty v-else-if="!workspace?.performances.length" description="本周没有演出场次，请先生成月度计划" />
    <el-card v-else shadow="never" class="matrix-card">
      <div class="matrix-scroll">
        <table class="schedule-matrix">
          <thead><tr><th class="sticky meta date-col">日期</th><th class="sticky meta slot-col">场次</th><th v-for="role in workspace.roles" :key="role.id" class="role-col"><strong>{{ role.name }}</strong><small v-if="role.group_name">{{ role.group_name }}</small></th></tr></thead>
          <tbody><tr v-for="performance in workspace.performances" :key="performance.id">
            <td class="sticky meta date-col"><strong>{{ formatDate(performance.performance_date) }}</strong><small>{{ weekday(performance.performance_date) }}</small></td>
            <td class="sticky meta slot-col"><span>{{ performance.slot_name }}</span><small>{{ performance.start_time.slice(0, 5) }}</small></td>
            <td v-for="role in workspace.roles" :key="role.id" :class="['assignment-cell', { 'has-conflict': cellConflicts(performance.id, role.id).length, 'has-warning': cellWarnings(performance.id, role.id).length }]">
              <select
                :aria-label="`${formatDate(performance.performance_date)} ${performance.slot_name} ${role.name}`"
                :value="actorIdAt(performance.id, role.id) ?? ''"
                @change="setActor(performance.id, role.id, Number(($event.target as HTMLSelectElement).value) || null)"
              >
                <option value="">待安排</option>
                <option v-for="actor in actorsFor(role.id)" :key="actor.id" :value="actor.id">{{ actor.display_name }} · 本周{{ actorWeeklyCount(actor.id) }}</option>
              </select>
              <el-tooltip v-if="cellConflicts(performance.id, role.id).length" :content="cellConflicts(performance.id, role.id).map(item => item.message).join('；')">
                <span class="conflict-dot">!</span>
              </el-tooltip>
              <el-tooltip v-else-if="cellWarnings(performance.id, role.id).length" :content="cellWarnings(performance.id, role.id).map(item => item.message).join('；')">
                <span class="warning-dot">!</span>
              </el-tooltip>
            </td>
          </tr></tbody>
        </table>
      </div>
    </el-card>

    <el-drawer v-model="conflictDrawer" title="冲突复核" size="420px">
      <el-alert title="以下冲突不会被自动忽略。确认后可强制保存或发布。" type="warning" :closable="false" show-icon />
      <div v-if="!pendingConflicts.length" class="no-conflicts"><el-icon><CircleCheck /></el-icon><strong>未发现冲突</strong></div>
      <div v-for="(item, index) in pendingConflicts" :key="`${item.code}-${index}`" class="conflict-item">
        <el-tag type="danger" effect="light">{{ conflictName(item.code) }}</el-tag><p>{{ item.message }}</p><small>{{ conflictLocation(item) }}</small>
      </div>
      <template #footer><el-button @click="conflictDrawer = false">取消</el-button><el-button v-if="pendingAction" type="danger" @click="confirmPersist">确认{{ pendingAction === 'publish' ? '发布' : '保存' }}</el-button></template>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ArrowLeft, ArrowRight, CircleCheck } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi, type ScheduleAssignment, type ScheduleConflict, type Theater, type WeeklyScheduleWorkspace } from "../../api/admin";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../auth/store";
import PageHeader from "../../components/PageHeader.vue";
import { assignmentKey, mergeRecommendations, mondayFor, shiftWeek, weekLabel } from "../../features/weekly-scheduling/workspace";

const auth = useAuthStore();
const theaters = ref<Theater[]>([]), theaterId = ref<number>(), weekStart = ref(mondayFor(new Date()));
const workspace = ref<WeeklyScheduleWorkspace>(), assignments = ref<ScheduleAssignment[]>([]);
const loading = ref(true), recommending = ref(false), validating = ref(false), saving = ref(false), publishing = ref(false);
const error = ref(""), conflictDrawer = ref(false), pendingConflicts = ref<ScheduleConflict[]>([]), pendingAction = ref<"draft" | "publish" | null>(null);
let autoValidationTimer: ReturnType<typeof setTimeout> | undefined;
let validationRevision = 0;
const token = () => auth.token as string;
const weekEnd = computed(() => { const next = shiftWeek(weekStart.value, 1); const value = new Date(`${next}T00:00:00`); value.setDate(value.getDate() - 1); return value.toISOString().slice(0, 10); });
const totalCells = computed(() => (workspace.value?.performances.length || 0) * (workspace.value?.roles.length || 0));
const assignedCount = computed(() => assignments.value.length);
const statusText = computed(() => ({ uncreated: "未保存", draft: "草稿", ready: "草稿", scheduled: "已发布" }[workspace.value?.status || "uncreated"]));
const statusType = computed(() => workspace.value?.status === "scheduled" ? "success" : "info");
const assignmentMap = computed(() => new Map(assignments.value.map(row => [assignmentKey(row.performance_id, row.role_id), row])));

async function loadWorkspace() {
  if (!theaterId.value) return;
  cancelAutoValidation();
  loading.value = true; error.value = "";
  try { workspace.value = await adminApi.getWeeklyScheduleWorkspace(token(), theaterId.value, weekStart.value); assignments.value = [...workspace.value.assignments]; }
  catch (err: any) { error.value = err.message || "加载周排班失败"; }
  finally { loading.value = false; }
}
async function changeWeek(offset: number) { weekStart.value = shiftWeek(weekStart.value, offset); await loadWorkspace(); }
function payload(confirmConflicts = false) { return { theater_id: theaterId.value!, week_start: weekStart.value, expected_version: workspace.value?.version || 0, assignments: assignments.value.map(({ conflict_codes: _, ...row }) => row), confirm_conflicts: confirmConflicts }; }
async function recommend() {
  recommending.value = true; error.value = "";
  try { const result = await adminApi.recommendWeeklySchedule(token(), payload()); assignments.value = mergeRecommendations(assignments.value, result.assignments); workspace.value = { ...result, assignments: assignments.value }; ElMessage.success("已补齐可安全推荐的空位"); }
  catch (err: any) { error.value = err.message || "推荐排班失败"; }
  finally { recommending.value = false; }
}
async function validate() {
  cancelAutoValidation();
  validating.value = true;
  try { const result = await adminApi.validateWeeklySchedule(token(), payload()); pendingConflicts.value = result.conflicts; pendingAction.value = null; conflictDrawer.value = true; if (!result.conflicts.length) ElMessage.success("冲突检测通过"); }
  catch (err: any) { error.value = err.message || "冲突检测失败"; }
  finally { validating.value = false; }
}
function conflictDetail(err: unknown) {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== "object") return null;
  const detail = err.detail as { code?: string; conflicts?: ScheduleConflict[] };
  return detail.code === "conflicts_require_confirmation" ? detail.conflicts || [] : null;
}
function isIncompletePerformanceError(err: unknown) {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== "object") return false;
  return (err.detail as { code?: string }).code === "incomplete_performances";
}
async function persist(publish: boolean, confirmed = false) {
  (publish ? publishing : saving).value = true; error.value = "";
  try {
    const result = publish ? await adminApi.publishWeeklySchedule(token(), payload(confirmed)) : await adminApi.saveWeeklyScheduleDraft(token(), payload(confirmed));
    workspace.value = result; assignments.value = [...result.assignments]; conflictDrawer.value = false; pendingAction.value = null;
    ElMessage.success(publish ? "排班已发布，演员端现在可见" : "草稿已保存");
  } catch (err: any) {
    if (isIncompletePerformanceError(err)) {
      await ElMessageBox.alert(
        "存在未完成角色安排的演出场次，请补充完整后再发布。",
        "无法发布排班",
        { confirmButtonText: "返回补充", type: "error" },
      );
      return;
    }
    const conflicts = conflictDetail(err);
    if (conflicts) { pendingConflicts.value = conflicts; pendingAction.value = publish ? "publish" : "draft"; conflictDrawer.value = true; }
    else error.value = err.message || (publish ? "发布失败" : "保存失败");
  } finally { (publish ? publishing : saving).value = false; }
}
async function confirmPersist() { await persist(pendingAction.value === "publish", true); }
function actorIdAt(performanceId: number, roleId: number) { return assignmentMap.value.get(assignmentKey(performanceId, roleId))?.actor_id; }
function setActor(performanceId: number, roleId: number, actorId: number | null) {
  const key = assignmentKey(performanceId, roleId); assignments.value = assignments.value.filter(row => assignmentKey(row.performance_id, row.role_id) !== key);
  if (actorId) assignments.value.push({ performance_id: performanceId, role_id: roleId, actor_id: actorId, source: "manual" });
  scheduleAutoValidation();
}
function cancelAutoValidation() {
  if (autoValidationTimer) clearTimeout(autoValidationTimer);
  autoValidationTimer = undefined;
  validationRevision += 1;
}
function scheduleAutoValidation() {
  if (autoValidationTimer) clearTimeout(autoValidationTimer);
  const revision = ++validationRevision;
  autoValidationTimer = setTimeout(async () => {
    autoValidationTimer = undefined;
    try {
      const result = await adminApi.validateWeeklySchedule(token(), payload());
      if (revision !== validationRevision || !workspace.value) return;
      workspace.value = {
        ...workspace.value,
        conflicts: result.conflicts,
        conflict_summary: result.conflicts.reduce<Record<string, number>>((summary, item) => {
          summary[item.code] = (summary[item.code] || 0) + 1;
          return summary;
        }, {}),
        warnings: result.warnings || [],
        warning_summary: (result.warnings || []).reduce<Record<string, number>>((summary, item) => {
          summary[item.code] = (summary[item.code] || 0) + 1;
          return summary;
        }, {}),
        empty_slots: result.empty_slots,
      };
    } catch (err: any) {
      if (revision === validationRevision) error.value = err.message || "自动冲突检测失败";
    }
  }, 300);
}
function actorsFor(roleId: number) { return workspace.value?.actors.filter(row => row.role_ids.includes(roleId) && row.rating_level !== "suspended") || []; }
function actorWeeklyCount(actorId: number) { return assignments.value.filter(row => row.actor_id === actorId).length; }
function cellConflicts(performanceId: number, roleId: number) { return workspace.value?.conflicts.filter(row => row.performance_id === performanceId && row.role_id === roleId) || []; }
function cellWarnings(performanceId: number, roleId: number) { return workspace.value?.warnings?.filter(row => row.performance_id === performanceId && row.role_id === roleId) || []; }
function formatDate(value: string) { const [, month, day] = value.split("-").map(Number); return `${month}月${day}日`; }
function weekday(value: string) { return `周${"日一二三四五六"[new Date(`${value}T00:00:00`).getDay()]}`; }
const conflictNames: Record<string, string> = { actor_on_leave: "请假冲突", duplicate_actor_performance: "同场冲突", role_not_allowed: "角色不匹配", consecutive_limit_exceeded: "连场超限", low_rating_monthly_cap_exceeded: "月度上限", actor_suspended: "演员停用" };
function conflictName(code: string) { return conflictNames[code] || code; }
function conflictLocation(item: ScheduleConflict) { const performance = workspace.value?.performances.find(row => row.id === item.performance_id); const role = workspace.value?.roles.find(row => row.id === item.role_id); const actor = workspace.value?.actors.find(row => row.id === item.actor_id); return [performance && `${formatDate(performance.performance_date)} ${performance.slot_name}`, role?.name, actor?.display_name].filter(Boolean).join(" · "); }

onMounted(async () => { try { theaters.value = await adminApi.getTheaters(token()); theaterId.value = theaters.value[0]?.id; await loadWorkspace(); } catch (err: any) { error.value = err.message || "加载剧场失败"; loading.value = false; } });
onBeforeUnmount(cancelAutoValidation);
</script>

<style scoped>
.scheduling-page { width: 100%; display: grid; gap: 16px; }
.toolbar-card :deep(.el-card__body) { padding: 14px 18px; }.toolbar { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.field { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 13px; }.week-nav { display: flex; align-items: center; gap: 10px; }.week-nav div { display: grid; gap: 2px; text-align: center; min-width: 205px; }.week-nav small { color: var(--text-secondary); }.week-nav strong { font-size: 15px; }
.status-block { display: flex; align-items: center; gap: 10px; color: var(--text-secondary); font-size: 13px; }.danger { color: #d64545; }.warning { color: #c47b08; }.actions { margin-left: auto; display: flex; gap: 8px; }
.matrix-card :deep(.el-card__body) { padding: 0; }.matrix-scroll { overflow: auto; max-height: calc(100vh - 310px); }.schedule-matrix { border-collapse: separate; border-spacing: 0; min-width: 100%; }
th, td { height: 68px; padding: 10px 12px; border-right: 1px solid #e5eaf1; border-bottom: 1px solid #e5eaf1; background: #fff; }.schedule-matrix thead th { position: sticky; top: 0; z-index: 4; height: 58px; background: #f7f9fc; color: var(--text-secondary); text-align: left; }
.sticky { position: sticky; z-index: 3; }.date-col { left: 0; width: 115px; min-width: 115px; }.slot-col { left: 115px; width: 105px; min-width: 105px; box-shadow: 8px 0 14px -14px #32415a; }.meta { background: #fbfcfe; }.meta strong, .meta span, .meta small, .role-col strong, .role-col small { display: block; }.meta small, .role-col small { margin-top: 4px; color: var(--text-secondary); font-size: 12px; }.role-col { min-width: 180px; }
.assignment-cell { position: relative; min-width: 180px; }.assignment-cell select { height: 38px; border-radius: 7px; padding: 0 30px 0 10px; background: #fff !important; }.assignment-cell.has-warning { background: #fffaf0; }.assignment-cell.has-warning select { border-color: #e7ad45 !important; }.assignment-cell.has-conflict { background: #fff7f6; }.assignment-cell.has-conflict select { border-color: #e86b63 !important; }.conflict-dot, .warning-dot { position: absolute; right: 16px; top: 6px; display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; color: white; font-size: 11px; font-weight: 700; }.conflict-dot { background: #e34c4c; }.warning-dot { background: #d99419; }
.conflict-item { margin-top: 14px; padding: 14px; border: 1px solid #f0cccc; border-radius: 9px; background: #fff8f7; }.conflict-item p { margin: 10px 0 6px; }.conflict-item small { color: var(--text-secondary); }.no-conflicts { min-height: 180px; display: grid; place-items: center; align-content: center; gap: 10px; color: #2b9a66; }.no-conflicts .el-icon { font-size: 34px; }
@media (max-width: 1000px) { .actions { width: 100%; margin-left: 0; }.matrix-scroll { max-height: none; } }
</style>
