<template>
  <section class="scheduling-page">
    <PageHeader title="周排班" description="按月连续查看和编辑各自然周排班，支持跨周校验、推荐、保存与发布。" />
    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />

    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-primary">
          <div class="field">
            <span>剧场</span>
            <el-select v-model="theaterId" aria-label="剧场" style="width: 220px" @change="requestTheaterChange">
              <el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </div>
          <div class="month-nav">
            <el-button aria-label="上个月" circle @click="requestMonthChange(-1)"><el-icon><ArrowLeft /></el-icon></el-button>
            <strong>{{ monthLabel }}</strong>
            <el-button aria-label="下个月" circle @click="requestMonthChange(1)"><el-icon><ArrowRight /></el-icon></el-button>
          </div>
          <el-button class="locate-button" @click="requestLocateCurrentWeek">定位本周</el-button>
        </div>

        <div class="toolbar-secondary">
          <div class="toolbar-summary">
            <div class="active-week">
              <small>当前操作周</small>
              <div class="week-switcher">
                <el-button aria-label="上一周" circle size="small" :disabled="loading" @click="requestWeekChange(-1)"><el-icon><ArrowLeft /></el-icon></el-button>
                <strong>{{ activeWeekLabel }}</strong>
                <el-button aria-label="下一周" circle size="small" :disabled="loading" @click="requestWeekChange(1)"><el-icon><ArrowRight /></el-icon></el-button>
              </div>
            </div>
            <div class="status-block">
              <span class="status-pill status-pill--state"><el-tag :type="statusType" effect="plain">{{ statusText }}</el-tag></span>
              <span class="status-pill">{{ counts.assigned }}/{{ counts.total }} 已安排</span>
              <span v-if="counts.conflicts" class="status-pill status-pill--danger">{{ counts.conflicts }} 个冲突</span>
              <span v-if="counts.warnings" class="status-pill status-pill--warning">{{ counts.warnings }} 个提醒</span>
            </div>
          </div>
          <div class="actions">
            <el-button :loading="recommending" :disabled="!activeWeek" @click="recommend">推荐当前周</el-button>
            <el-button :loading="validating" :disabled="!Object.keys(monthState).length" @click="validateMonth(true)">检测整月冲突</el-button>
            <el-button :loading="saving" :disabled="!dirtyWeeks.length" @click="saveAllDrafts">{{ saveButtonText }}</el-button>
            <el-button type="primary" :loading="publishing" :disabled="!activeWeek" @click="persistActive(true)">
              发布 {{ compactWeekLabel }}
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-empty v-else-if="!theaters.length" description="请先新增剧场" />
    <el-empty v-else-if="!activeWeek?.workspace.performances.length" description="本周没有演出场次，请先生成月度计划" />
    <el-card v-else shadow="never" class="matrix-card">
      <div class="matrix-scroll">
        <table class="schedule-matrix">
          <thead>
            <tr>
              <th class="sticky meta date-col">日期</th>
              <th class="sticky meta slot-col">场次</th>
              <th v-for="role in activeWeek.workspace.roles" :key="role.id" class="role-col">
                <strong>{{ role.name }}</strong>
                <small v-if="role.group_name">{{ role.group_name }}</small>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="performance in activeWeek.workspace.performances" :key="performance.id">
              <td class="sticky meta date-col">
                <strong>{{ formatDate(performance.performance_date) }}</strong>
                <small>{{ weekday(performance.performance_date) }}</small>
              </td>
              <td class="sticky meta slot-col">
                <span>{{ performance.slot_name }}</span>
                <small>{{ performance.start_time.slice(0, 5) }}</small>
              </td>
              <td
                v-for="role in activeWeek.workspace.roles"
                :key="role.id"
                :class="['assignment-cell', { 'has-conflict': cellConflicts(performance.id, role.id).length, 'has-warning': cellWarnings(performance.id, role.id).length }]"
              >
                <select
                  :aria-label="`${formatDate(performance.performance_date)} ${performance.slot_name} ${role.name}`"
                  :value="actorIdAt(performance.id, role.id) ?? ''"
                  :disabled="isLocked(performance.id, role.id)"
                  @change="setActor(performance.performance_date, performance.id, role.id, Number(($event.target as HTMLSelectElement).value) || null)"
                >
                  <option value="">待安排</option>
                  <option v-for="actor in actorsFor(performance.performance_date, role.id)" :key="actor.id" :value="actor.id">
                    {{ actor.display_name }} · 本周{{ actorWeeklyCount(performance.performance_date, actor.id) }}
                  </option>
                </select>
                <button v-if="lockedAt(performance.id, role.id)" type="button" class="designation-lock"
                  :aria-label="`查看指定 ${lockedAt(performance.id, role.id)!.designation_id} 详情`"
                  @click="openDesignation(lockedAt(performance.id, role.id)!.designation_id!, performance.id)">
                  预指定锁定 · {{ designationTypeName(lockedAt(performance.id, role.id)!.designation_type) }}道具
                  · 持有人 {{ lockedAt(performance.id, role.id)!.owner_player_name }}
                  · 使用玩家 {{ lockedAt(performance.id, role.id)!.beneficiary_player_name }}
                  · {{ lockedAt(performance.id, role.id)!.entitlement_serial || "旧数据无券号" }}
                </button>
                <el-tooltip v-if="cellConflicts(performance.id, role.id).length" :content="cellConflicts(performance.id, role.id).map(row => row.message).join('；')">
                  <span class="conflict-dot">!</span>
                </el-tooltip>
                <el-tooltip v-else-if="cellWarnings(performance.id, role.id).length" :content="cellWarnings(performance.id, role.id).map(row => row.message).join('；')">
                  <span class="warning-dot">!</span>
                </el-tooltip>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </el-card>

    <el-drawer v-model="conflictDrawer" title="冲突复核" size="420px">
      <el-alert title="以下冲突不会被自动忽略。确认后可强制保存或发布。" type="warning" :closable="false" show-icon />
      <div v-if="!pendingConflicts.length" class="no-conflicts"><el-icon><CircleCheck /></el-icon><strong>未发现冲突</strong></div>
      <div v-for="(item, index) in pendingConflicts" :key="`${item.code}-${index}`" class="conflict-item">
        <el-tag type="danger" effect="light">{{ conflictName(item.code) }}</el-tag><p>{{ item.message }}</p><small>{{ conflictLocation(item) }}</small>
      </div>
      <template #footer>
        <el-button @click="conflictDrawer = false">取消</el-button>
        <el-button v-if="pendingAction" type="danger" @click="confirmPersist">确认{{ pendingAction === 'publish' ? '发布' : '保存' }}</el-button>
      </template>
    </el-drawer>

    <el-dialog v-model="navigationGuardVisible" title="存在未保存的排班修改" width="430px" :close-on-click-modal="false">
      <p>切换后将离开当前月份，请先处理未保存修改。</p>
      <template #footer>
        <el-button @click="cancelNavigation">取消</el-button>
        <el-button @click="discardAndNavigate">放弃修改</el-button>
        <el-button type="primary" :loading="saving" @click="saveAndNavigate">保存后切换</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, CircleCheck } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi, type ScheduleAssignment, type ScheduleConflict, type Theater } from "../../api/admin";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../auth/store";
import PageHeader from "../../components/PageHeader.vue";
import {
  aggregateScheduleCounts, contextWeeks, createMonthState, dirtyWeekStarts,
  performanceWeekMap, replaceWeekAssignments, type MonthScheduleState,
} from "../../features/weekly-scheduling/month-workspace";
import {
  assignmentKey, isoDate, mergeRecommendations, mondayFor,
  monthWeekStarts, weekEnd, weekLabel, weekStartForDate,
} from "../../features/weekly-scheduling/workspace";

const auth = useAuthStore();
const router = useRouter();
const now = new Date();
const today = isoDate(now);
const theaters = ref<Theater[]>([]);
const theaterId = ref<number>();
const loadedTheaterId = ref<number>();
const selectedYear = ref(now.getFullYear());
const selectedMonth = ref(now.getMonth() + 1);
const activeWeekStart = ref(mondayFor(now));
const monthState = ref<MonthScheduleState>({});
const loading = ref(true), recommending = ref(false), validating = ref(false), saving = ref(false), publishing = ref(false);
const error = ref(""), conflictDrawer = ref(false), pendingConflicts = ref<ScheduleConflict[]>([]), pendingAction = ref<"draft" | "draft-batch" | "publish" | null>(null);
const pendingDraftWeeks = ref<string[]>([]);
const navigationGuardVisible = ref(false);
let autoValidationTimer: ReturnType<typeof setTimeout> | undefined;
let validationRevision = 0;
let pendingNavigation: (() => Promise<void>) | null = null;

const token = () => auth.token as string;
const monthLabel = computed(() => `${selectedYear.value} 年 ${selectedMonth.value} 月`);
const activeWeek = computed(() => monthState.value[activeWeekStart.value]);
const activeWeekLabel = computed(() => weekLabel(activeWeekStart.value, weekEnd(activeWeekStart.value)));
const compactWeekLabel = computed(() => {
  const start = activeWeekStart.value.split("-").map(Number);
  const end = weekEnd(activeWeekStart.value).split("-").map(Number);
  return `${start[1]}月${start[2]}日–${end[1]}月${end[2]}日`;
});
const counts = computed(() => activeWeek.value ? aggregateScheduleCounts({ [activeWeekStart.value]: activeWeek.value }) : { assigned: 0, total: 0, conflicts: 0, warnings: 0 });
const dirtyWeeks = computed(() => dirtyWeekStarts(monthState.value));
const saveButtonText = computed(() => dirtyWeeks.value.length ? `保存草稿（${dirtyWeeks.value.length} 周）` : "保存草稿");
const statusText = computed(() => ({ uncreated: "未保存", draft: "草稿", ready: "草稿", scheduled: "已发布" }[activeWeek.value?.workspace.status || "uncreated"]));
const statusType = computed(() => activeWeek.value?.workspace.status === "scheduled" ? "success" : "info");
const assignmentMap = computed(() => new Map(Object.values(monthState.value).flatMap((week) => week.assignments.map((row) => [assignmentKey(row.performance_id, row.role_id), row] as const))));

async function loadMonth(preferredWeek?: string) {
  if (!theaterId.value) return;
  cancelAutoValidation();
  loading.value = true;
  error.value = "";
  const starts = monthWeekStarts(selectedYear.value, selectedMonth.value);
  try {
    const results = await Promise.all(starts.map((start) => adminApi.getWeeklyScheduleWorkspace(token(), theaterId.value!, start)));
    monthState.value = createMonthState(results);
    loadedTheaterId.value = theaterId.value;
    const currentWeek = weekStartForDate(today);
    activeWeekStart.value = preferredWeek && starts.includes(preferredWeek)
      ? preferredWeek
      : starts.includes(currentWeek) ? currentWeek : starts[0];
  } catch (err: any) {
    error.value = err.message || "加载月排班失败";
  } finally {
    loading.value = false;
  }
}

async function changeMonth(offset: number) {
  const value = new Date(selectedYear.value, selectedMonth.value - 1 + offset, 1);
  selectedYear.value = value.getFullYear();
  selectedMonth.value = value.getMonth() + 1;
  await loadMonth();
}

function requestMonthChange(offset: number) {
  if (!dirtyWeeks.value.length) return changeMonth(offset);
  pendingNavigation = () => changeMonth(offset);
  navigationGuardVisible.value = true;
}

function shiftedWeekStart(offset: number) {
  const [year, month, day] = activeWeekStart.value.split("-").map(Number);
  return isoDate(new Date(year, month - 1, day + offset * 7));
}

async function changeWeek(offset: number) {
  const targetWeek = shiftedWeekStart(offset);
  if (monthWeekStarts(selectedYear.value, selectedMonth.value).includes(targetWeek)) {
    activeWeekStart.value = targetWeek;
    return;
  }
  const [year, month] = targetWeek.split("-").map(Number);
  selectedYear.value = year;
  selectedMonth.value = month;
  await loadMonth(targetWeek);
}

function requestWeekChange(offset: number) {
  if (!dirtyWeeks.value.length) return changeWeek(offset);
  pendingNavigation = () => changeWeek(offset);
  navigationGuardVisible.value = true;
}

function cancelNavigation() {
  navigationGuardVisible.value = false;
  pendingNavigation = null;
}

async function discardAndNavigate() {
  const action = pendingNavigation;
  cancelNavigation();
  await action?.();
}

async function saveAndNavigate() {
  const action = pendingNavigation;
  if (!await saveAllDrafts()) return;
  cancelNavigation();
  await action?.();
}

async function locateCurrentWeek() {
  const current = new Date();
  selectedYear.value = current.getFullYear();
  selectedMonth.value = current.getMonth() + 1;
  await loadMonth();
}

function requestLocateCurrentWeek() {
  if (!dirtyWeeks.value.length) return locateCurrentWeek();
  pendingNavigation = locateCurrentWeek;
  navigationGuardVisible.value = true;
}

function requestTheaterChange(nextTheaterId: number) {
  const previousTheaterId = loadedTheaterId.value;
  if (!dirtyWeeks.value.length) return loadMonth();
  theaterId.value = previousTheaterId;
  pendingNavigation = async () => {
    theaterId.value = nextTheaterId;
    await loadMonth();
  };
  navigationGuardVisible.value = true;
}

function weekForDate(date: string) { return monthState.value[weekStartForDate(date)]; }
function actorsFor(date: string, roleId: number) { return weekForDate(date)?.workspace.actors.filter((row) => row.role_ids.includes(roleId) && row.rating_level !== "suspended") || []; }
function actorIdAt(performanceId: number, roleId: number) { return assignmentMap.value.get(assignmentKey(performanceId, roleId))?.actor_id; }
function lockedAt(performanceId: number, roleId: number) { const row = assignmentMap.value.get(assignmentKey(performanceId, roleId)); return row?.locked ? row : undefined; }
function isLocked(performanceId: number, roleId: number) { return Boolean(lockedAt(performanceId, roleId)); }
function designationTypeName(value?: string | null) { return ({ universal: "万能", top_three: "前三", paired: "成对" } as Record<string, string>)[value || ""] || "指定"; }
function openDesignation(id: number, performanceId: number) { router.push({ name: "admin-designations-wishes", query: { performance_id: String(performanceId), review_tab: "designations", designation_id: String(id) } }); }
function actorWeeklyCount(date: string, actorId: number) { return weekForDate(date)?.assignments.filter((row) => row.actor_id === actorId).length || 0; }

function setActor(date: string, performanceId: number, roleId: number, actorId: number | null) {
  if (isLocked(performanceId, roleId)) return;
  const weekStart = weekStartForDate(date);
  activeWeekStart.value = weekStart;
  const week = monthState.value[weekStart];
  if (!week) return;
  const key = assignmentKey(performanceId, roleId);
  const assignments = week.assignments.filter((row) => assignmentKey(row.performance_id, row.role_id) !== key);
  if (actorId) assignments.push({ performance_id: performanceId, role_id: roleId, actor_id: actorId, source: "manual" });
  monthState.value = replaceWeekAssignments(monthState.value, weekStart, assignments);
  scheduleAutoValidation();
}

function payload(weekStart: string, confirmConflicts = false, confirmationToken?: string, idempotencyKey?: string) {
  const week = monthState.value[weekStart];
  return {
    theater_id: theaterId.value!,
    week_start: weekStart,
    expected_version: week.workspace.version,
    assignments: week.assignments.map(({ conflict_codes: _, locked: _locked, designation_id: _designationId,
      designation_type: _designationType, owner_player_name: _ownerName, beneficiary_player_name: _beneficiaryName,
      entitlement_serial: _serial, legacy_identity_fallback: _fallback, ...row }) => row),
    confirm_conflicts: confirmConflicts,
    confirmation_token: confirmationToken,
    idempotency_key: idempotencyKey,
  };
}

async function validateMonth(showDrawer = false) {
  if (!theaterId.value) return;
  cancelAutoValidation();
  validating.value = showDrawer;
  try {
    const result = await adminApi.validateScheduleContext(token(), { theater_id: theaterId.value, weeks: contextWeeks(monthState.value) });
    applyValidation(result.conflicts, result.warnings, result.empty_slots);
    if (showDrawer) {
      pendingConflicts.value = result.conflicts;
      pendingAction.value = null;
      conflictDrawer.value = true;
      if (!result.conflicts.length) ElMessage.success("整月冲突检测通过");
    }
  } catch (err: any) {
    error.value = err.message || "冲突检测失败";
  } finally {
    validating.value = false;
  }
}

function applyValidation(conflicts: ScheduleConflict[], warnings: ScheduleConflict[], emptySlots: { performance_id: number; role_id: number }[]) {
  const owner = performanceWeekMap(monthState.value);
  const next = { ...monthState.value };
  for (const [weekStart, week] of Object.entries(next)) {
    next[weekStart] = {
      ...week,
      workspace: {
        ...week.workspace,
        conflicts: conflicts.filter((item) => item.performance_id != null && owner.get(item.performance_id) === weekStart),
        warnings: warnings.filter((item) => item.performance_id != null && owner.get(item.performance_id) === weekStart),
        empty_slots: emptySlots.filter((item) => owner.get(item.performance_id) === weekStart),
      },
    };
  }
  monthState.value = next;
}

function scheduleAutoValidation() {
  if (autoValidationTimer) clearTimeout(autoValidationTimer);
  const revision = ++validationRevision;
  autoValidationTimer = setTimeout(async () => {
    autoValidationTimer = undefined;
    if (!theaterId.value) return;
    try {
      const result = await adminApi.validateScheduleContext(token(), { theater_id: theaterId.value, weeks: contextWeeks(monthState.value) });
      if (revision !== validationRevision) return;
      applyValidation(result.conflicts, result.warnings || [], result.empty_slots);
    } catch (err: any) {
      if (revision === validationRevision) error.value = err.message || "自动冲突检测失败";
    }
  }, 300);
}

function cancelAutoValidation() {
  if (autoValidationTimer) clearTimeout(autoValidationTimer);
  autoValidationTimer = undefined;
  validationRevision += 1;
}

async function recommend() {
  if (!activeWeek.value) return;
  recommending.value = true;
  error.value = "";
  try {
    const otherWeeks = contextWeeks(monthState.value).filter((week) => week.week_start !== activeWeekStart.value);
    const result = await adminApi.recommendWeeklySchedule(token(), { ...payload(activeWeekStart.value), context_weeks: otherWeeks });
    const merged = mergeRecommendations(activeWeek.value.assignments, result.assignments);
    monthState.value = replaceWeekAssignments(monthState.value, activeWeekStart.value, merged);
    await validateMonth();
    ElMessage.success("已补齐当前周可安全推荐的空位");
  } catch (err: any) {
    error.value = err.message || "推荐排班失败";
  } finally {
    recommending.value = false;
  }
}

async function saveAllDrafts() {
  if (!dirtyWeeks.value.length) return true;
  saving.value = true;
  error.value = "";
  const starts = dirtyWeeks.value;
  const results = await Promise.allSettled(starts.map((start) => adminApi.saveWeeklyScheduleDraft(token(), payload(start))));
  const next = { ...monthState.value };
  const failed: string[] = [];
  const conflictWeeks: string[] = [];
  const conflicts: ScheduleConflict[] = [];
  results.forEach((result, index) => {
    const start = starts[index];
    if (result.status === "fulfilled") {
      next[start] = createMonthState([result.value])[start];
    } else {
      const detail = conflictDetail(result.reason);
      if (detail) {
        conflictWeeks.push(start);
        conflicts.push(...detail);
      } else failed.push(weekLabel(start, weekEnd(start)));
    }
  });
  monthState.value = next;
  saving.value = false;
  if (conflictWeeks.length) {
    pendingDraftWeeks.value = conflictWeeks;
    pendingConflicts.value = conflicts;
    pendingAction.value = "draft-batch";
    conflictDrawer.value = true;
  }
  if (failed.length) error.value = `以下周保存失败：${failed.join("、")}`;
  else if (!conflictWeeks.length) ElMessage.success("所有修改已保存为草稿");
  return failed.length === 0 && conflictWeeks.length === 0;
}

async function saveConfirmedDrafts() {
  const starts = [...pendingDraftWeeks.value];
  saving.value = true;
  error.value = "";
  const results = await Promise.allSettled(starts.map((start) => adminApi.saveWeeklyScheduleDraft(token(), payload(start, true))));
  const next = { ...monthState.value };
  const failed: string[] = [];
  results.forEach((result, index) => {
    const start = starts[index];
    if (result.status === "fulfilled") next[start] = createMonthState([result.value])[start];
    else failed.push(weekLabel(start, weekEnd(start)));
  });
  monthState.value = next;
  saving.value = false;
  if (failed.length) {
    error.value = `以下冲突周保存失败：${failed.join("、")}`;
    return;
  }
  conflictDrawer.value = false;
  pendingAction.value = null;
  pendingDraftWeeks.value = [];
  ElMessage.success("已确认冲突并保存草稿");
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
function unmetDesignationDetail(err: unknown) {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== "object") return null;
  const detail = err.detail as { code?: string; confirmation_token?: string; idempotency_key?: string; designations?: { id: number; player_name: string; failure_reason: string; refund_target: string; refund_status: string; entitlement_serial?: string }[] };
  return detail.code === "unmet_designations_require_confirmation" ? detail : null;
}

async function persistActive(publish: boolean, confirmed = false) {
  if (!activeWeek.value) return;
  (publish ? publishing : saving).value = true;
  error.value = "";
  try {
    const result = publish
      ? await adminApi.publishWeeklySchedule(token(), payload(activeWeekStart.value, confirmed))
      : await adminApi.saveWeeklyScheduleDraft(token(), payload(activeWeekStart.value, confirmed));
    monthState.value = { ...monthState.value, [activeWeekStart.value]: createMonthState([result])[result.week_start] };
    conflictDrawer.value = false;
    pendingAction.value = null;
    ElMessage.success(publish ? "排班已发布，演员端现在可见" : "草稿已保存");
  } catch (err: any) {
    if (isIncompletePerformanceError(err)) {
      await ElMessageBox.alert("存在未完成角色安排的演出场次，请补充完整后再发布。", "无法发布排班", { confirmButtonText: "返回补充", type: "error" });
      return;
    }
    const unmet = unmetDesignationDetail(err);
    if (publish && unmet?.designations?.length) {
      const lines = unmet.designations.map((row) => `#${row.id} ${row.player_name}：${row.failure_reason}；${row.entitlement_serial || "无券号"}退回 ${row.refund_target}（${row.refund_status === "expired" ? "已过期" : "可用"}）`).join("\n");
      try {
        await ElMessageBox.confirm(lines, `有 ${unmet.designations.length} 条指定未满足`, { confirmButtonText: "确认发布并退回", cancelButtonText: "取消", type: "warning" });
        const result = await adminApi.publishWeeklySchedule(token(), payload(activeWeekStart.value, confirmed, unmet.confirmation_token, unmet.idempotency_key));
        monthState.value = { ...monthState.value, [activeWeekStart.value]: createMonthState([result])[result.week_start] };
        ElMessage.success("排班已发布，未满足指定已按列表退回");
      } catch (confirmError) {
        if (confirmError instanceof ApiError) error.value = (confirmError.detail as any)?.code === "stale_confirmation" ? "指定或退款范围已变更，请重新发布并确认。" : confirmError.message;
      }
      return;
    }
    const conflicts = conflictDetail(err);
    if (conflicts) {
      pendingConflicts.value = conflicts;
      pendingAction.value = publish ? "publish" : "draft";
      conflictDrawer.value = true;
    } else error.value = err.message || (publish ? "发布失败" : "保存失败");
  } finally {
    (publish ? publishing : saving).value = false;
  }
}

async function confirmPersist() {
  if (pendingAction.value === "draft-batch") await saveConfirmedDrafts();
  else await persistActive(pendingAction.value === "publish", true);
}
function cellConflicts(performanceId: number, roleId: number) { return Object.values(monthState.value).flatMap((week) => week.workspace.conflicts).filter((row) => row.performance_id === performanceId && row.role_id === roleId); }
function cellWarnings(performanceId: number, roleId: number) { return Object.values(monthState.value).flatMap((week) => week.workspace.warnings).filter((row) => row.performance_id === performanceId && row.role_id === roleId); }
function formatDate(value: string) { const [, month, day] = value.split("-").map(Number); return `${month}月${day}日`; }
function weekday(value: string) { return `周${"日一二三四五六"[new Date(`${value}T00:00:00`).getDay()]}`; }
const conflictNames: Record<string, string> = { actor_on_leave: "请假冲突", duplicate_actor_performance: "同场冲突", actor_already_in_performance: "同场冲突", role_not_allowed: "角色不匹配", consecutive_limit_exceeded: "连场超限", low_rating_monthly_cap_exceeded: "月度上限", low_rating_cap_reached: "月度上限", actor_suspended: "演员停用" };
function conflictName(code: string) { return conflictNames[code] || code; }
function conflictLocation(item: ScheduleConflict) {
  const states = Object.values(monthState.value);
  const performance = states.flatMap((week) => week.workspace.performances).find((row) => row.id === item.performance_id);
  const role = states.flatMap((week) => week.workspace.roles).find((row) => row.id === item.role_id);
  const actor = states.flatMap((week) => week.workspace.actors).find((row) => row.id === item.actor_id);
  return [performance && `${formatDate(performance.performance_date)} ${performance.slot_name}`, role?.name, actor?.display_name].filter(Boolean).join(" · ");
}

onMounted(async () => {
  try {
    theaters.value = await adminApi.getTheaters(token());
    theaterId.value = theaters.value[0]?.id;
    await loadMonth();
  } catch (err: any) {
    error.value = err.message || "加载剧场失败";
    loading.value = false;
  }
});
onBeforeUnmount(cancelAutoValidation);
</script>

<style scoped>
.scheduling-page { width: 100%; min-width: 0; display: grid; gap: 16px; }
.toolbar-card { position: sticky; top: 0; z-index: 10; overflow: visible; }.toolbar-card :deep(.el-card__body) { padding: 16px 18px; }
.toolbar { display: grid; gap: 12px; }.toolbar-primary, .toolbar-secondary, .toolbar-summary, .field, .month-nav, .status-block, .actions { display: flex; align-items: center; }.toolbar-primary { gap: 14px; justify-content: flex-start; }.toolbar-secondary { gap: 18px; min-width: 0; padding-top: 12px; border-top: 1px solid #edf0f5; }.toolbar-summary { min-width: 0; gap: 18px; }.field { gap: 9px; color: var(--text-secondary); font-size: 13px; white-space: nowrap; }.month-nav { gap: 8px; padding-left: 14px; border-left: 1px solid #e4e9f1; }.month-nav strong { min-width: 116px; text-align: center; color: var(--text-primary); font-size: 18px; letter-spacing: .02em; }.locate-button { margin-left: 2px; }.active-week { display: grid; min-width: 260px; gap: 4px; }.active-week small { color: var(--text-secondary); font-size: 12px; }.active-week strong { color: var(--text-primary); font-size: 14px; white-space: nowrap; }.week-switcher { display: flex; align-items: center; gap: 9px; }.week-switcher :deep(.el-button) { flex: 0 0 auto; }.status-block { flex-wrap: wrap; gap: 7px; color: var(--text-secondary); font-size: 12px; }.status-pill { display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border: 1px solid #e3e8f0; border-radius: 999px; background: #f7f9fc; white-space: nowrap; }.status-pill--state { padding: 0; border: 0; background: transparent; }.status-pill--state :deep(.el-tag) { height: 28px; border-radius: 999px; padding: 0 11px; }.status-pill--danger { border-color: #ffd5d2; background: #fff4f3; color: #d64545; }.status-pill--warning { border-color: #f7dfb4; background: #fff9ed; color: #b86d00; }.actions { margin-left: auto; flex: 0 0 auto; gap: 8px; }.actions :deep(.el-button) { min-height: 36px; margin-left: 0; }
.matrix-card :deep(.el-card__body) { padding: 0; }.matrix-scroll { max-height: calc(100vh - 300px); overflow: auto; scrollbar-color: #91a5bf #e6ebf2; scrollbar-width: thin; }.matrix-scroll::-webkit-scrollbar { width: 10px; height: 10px; }.matrix-scroll::-webkit-scrollbar-track { background: #e6ebf2; }.matrix-scroll::-webkit-scrollbar-thumb { border: 2px solid #e6ebf2; border-radius: 999px; background: #91a5bf; }.schedule-matrix { min-width: 100%; border-collapse: separate; border-spacing: 0; }.schedule-matrix th, .schedule-matrix td { height: 68px; padding: 10px 12px; border-right: 1px solid #e5eaf1; border-bottom: 1px solid #e5eaf1; background: #fff; }.schedule-matrix thead th { position: sticky; top: 0; z-index: 4; height: 58px; background: #f7f9fc; color: var(--text-secondary); text-align: left; }.sticky { position: sticky; z-index: 3; }.date-col { left: 0; width: 115px; min-width: 115px; }.slot-col { left: 115px; width: 105px; min-width: 105px; box-shadow: 8px 0 14px -14px #32415a; }.meta { background: #fbfcfe !important; }.meta strong, .meta span, .meta small, .role-col strong, .role-col small { display: block; }.meta small, .role-col small { margin-top: 4px; color: var(--text-secondary); font-size: 12px; }.role-col { min-width: 180px; }.assignment-cell { position: relative; min-width: 180px; }.assignment-cell select { width: 100%; height: 38px; padding: 0 30px 0 10px; border: 1px solid #d4dce8; border-radius: 7px; background: #fff; color: var(--text-primary); }.assignment-cell.has-warning { background: #fffaf0; }.assignment-cell.has-warning select { border-color: #e7ad45; }.assignment-cell.has-conflict { background: #fff7f6; }.assignment-cell.has-conflict select { border-color: #e86b63; }
.conflict-dot, .warning-dot { position: absolute; right: 16px; top: 6px; display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 700; }.conflict-dot { background: #e34c4c; }.warning-dot { background: #d99419; }
.conflict-item { margin-top: 14px; padding: 14px; border: 1px solid #f0cccc; border-radius: 9px; background: #fff8f7; }.conflict-item p { margin: 10px 0 6px; }.conflict-item small { color: var(--text-secondary); }.no-conflicts { min-height: 180px; display: grid; place-items: center; align-content: center; gap: 10px; color: #2b9a66; }.no-conflicts .el-icon { font-size: 34px; }
@media (max-width: 1380px) { .toolbar-secondary { align-items: flex-start; flex-direction: column; }.actions { width: 100%; margin-left: 0; justify-content: flex-end; } }
@media (max-width: 1100px) { .toolbar-card { position: static; }.toolbar-primary { flex-wrap: wrap; }.toolbar-summary { width: 100%; align-items: flex-start; flex-direction: column; gap: 10px; }.actions { justify-content: flex-start; flex-wrap: wrap; } }
@media (max-width: 720px) { .toolbar-card :deep(.el-card__body) { padding: 14px; }.toolbar-primary { align-items: stretch; flex-direction: column; }.month-nav { padding-left: 0; border-left: 0; }.field :deep(.el-select) { width: 100% !important; }.active-week { min-width: 0; }.actions :deep(.el-button) { flex: 1 1 140px; } }
</style>
