<template>
  <section class="monthly-page">
    <PageHeader title="月度计划" description="直接在日历中开启或关闭每天的演出场次。" />
    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
    <el-alert v-if="success" :title="success" type="success" show-icon closable @close="success = ''" />

    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-group">
          <span class="label">剧场</span>
          <el-select v-model="selectedTheaterId" style="width: 220px" @change="changeTheater">
            <el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </div>
        <div class="month-nav">
          <el-button aria-label="上一月" circle @click="changeMonth(-1)"><el-icon><ArrowLeft /></el-icon></el-button>
          <strong>{{ year }}年{{ month }}月</strong>
          <el-button aria-label="下一月" circle @click="changeMonth(1)"><el-icon><ArrowRight /></el-icon></el-button>
        </div>
        <div class="summary">
          <span><b>{{ openDays }}</b> 开演天</span><span><b>{{ closedDays }}</b> 闭店天</span><span><b>{{ performanceCount }}</b> 场</span>
        </div>
        <div class="actions">
          <el-button :disabled="!selectedTheaterId" @click="resetFromTemplate">按周模板重置</el-button>
          <el-button type="primary" :loading="saving" :disabled="!selectedTheaterId" @click="save">生成月度计划</el-button>
        </div>
      </div>
    </el-card>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-empty v-else-if="!theaters.length" description="请先在基础配置中新增剧场" />
    <el-empty v-else-if="!slots.length" description="该剧场还没有可用场次，请先配置场次" />
    <MonthlyCalendarEditor
      v-else
      v-model="draft"
      :year="year"
      :month="month"
      :slots="slots"
      :weekly-template="weeklyTemplate"
      :persisted-dates="persistedDates"
      @dirty="dirty = true"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, ArrowRight } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { adminApi, type Performance, type Theater, type TheaterSlot, type WeeklyTemplate } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import MonthlyCalendarEditor from "../../components/admin/MonthlyCalendarEditor.vue";
import PageHeader from "../../components/PageHeader.vue";
import { buildCalendarDraft, nextMonth, serializeDraft, type MonthlyCalendarDraft } from "../../features/monthly-plan/calendarDraft";

const initial = nextMonth(new Date());
const auth = useAuthStore();
const theaters = ref<Theater[]>([]), slots = ref<TheaterSlot[]>([]), performances = ref<Performance[]>([]);
const weeklyTemplate = ref<WeeklyTemplate>({}), draft = ref<MonthlyCalendarDraft>({});
const selectedTheaterId = ref<number>(), committedTheaterId = ref<number>();
const year = ref(initial.year), month = ref(initial.month);
const loading = ref(true), saving = ref(false), dirty = ref(false), error = ref(""), success = ref("");
const performanceCount = computed(() => Object.values(draft.value).reduce((sum, ids) => sum + ids.length, 0));
const persistedDates = computed(() => [...new Set(performances.value.map((item) => item.performance_date))]);
const openDays = computed(() => Object.values(draft.value).filter((ids) => ids.length).length);
const closedDays = computed(() => Object.keys(draft.value).length - openDays.value);
const token = () => auth.token as string;
const conflictMessages: Record<string, string> = {
  monthly_plan_has_non_draft_performances: "该月存在已发布场次，无法直接移除。",
  monthly_plan_has_referenced_performances: "该月存在已排班或已指定场次，请先处理引用。",
};

async function confirmDiscard() {
  if (!dirty.value) return true;
  try { await ElMessageBox.confirm("当前月份有未保存修改，确定放弃？", "切换计划", { type: "warning" }); return true; }
  catch { return false; }
}
async function loadCalendar() {
  if (!selectedTheaterId.value) return;
  loading.value = true; error.value = "";
  try {
    [slots.value, weeklyTemplate.value, performances.value] = await Promise.all([
      adminApi.getTheaterSlots(token(), selectedTheaterId.value),
      adminApi.getWeeklyTemplate(token(), selectedTheaterId.value),
      adminApi.getPerformances(token(), selectedTheaterId.value, year.value, month.value),
    ]);
    draft.value = buildCalendarDraft({ year: year.value, month: month.value, template: weeklyTemplate.value, performances: performances.value });
    dirty.value = false; committedTheaterId.value = selectedTheaterId.value;
  } catch (err: any) { error.value = err.message || "加载月度计划失败"; }
  finally { loading.value = false; }
}
async function changeMonth(offset: number) {
  if (!(await confirmDiscard())) return;
  const value = new Date(year.value, month.value - 1 + offset, 1);
  year.value = value.getFullYear(); month.value = value.getMonth() + 1;
  await loadCalendar();
}
async function changeTheater(value: number) {
  if (!(await confirmDiscard())) { selectedTheaterId.value = committedTheaterId.value; return; }
  selectedTheaterId.value = value; await loadCalendar();
}
async function resetFromTemplate() {
  try { await ElMessageBox.confirm("将整月恢复为默认周模板？", "重置月度计划", { type: "warning" }); }
  catch { return; }
  draft.value = buildCalendarDraft({ year: year.value, month: month.value, template: weeklyTemplate.value, performances: [] }); dirty.value = true;
}
async function save() {
  if (!selectedTheaterId.value) return;
  saving.value = true; error.value = ""; success.value = "";
  try {
    const submittedDraft = Object.fromEntries(
      Object.entries(draft.value).map(([date, slotIds]) => [date, [...slotIds]]),
    );
    performances.value = await adminApi.replaceMonthlyPlan(token(), { theater_id: selectedTheaterId.value, year: year.value, month: month.value, days: serializeDraft(draft.value) });
    draft.value = performances.value.length
      ? buildCalendarDraft({ year: year.value, month: month.value, template: weeklyTemplate.value, performances: performances.value })
      : submittedDraft;
    dirty.value = false; success.value = "月度计划已生成";
  } catch (err: any) { error.value = conflictMessages[err.message] || err.message || "生成月度计划失败"; }
  finally { saving.value = false; }
}
onMounted(async () => {
  try { theaters.value = await adminApi.getTheaters(token()); selectedTheaterId.value = theaters.value[0]?.id; committedTheaterId.value = selectedTheaterId.value; await loadCalendar(); }
  catch (err: any) { error.value = err.message || "加载剧场失败"; loading.value = false; }
});
</script>

<style scoped>
.monthly-page { max-width: 1500px; margin: 0 auto; display: grid; gap: 16px; }
.toolbar-card :deep(.el-card__body) { padding: 14px 18px; }
.toolbar { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
.toolbar-group { display: flex; align-items: center; gap: 9px; }.label { color: var(--text-secondary); font-size: 13px; }
.month-nav { display: flex; align-items: center; gap: 12px; min-width: 180px; justify-content: center; }.month-nav strong { font-size: 18px; }
.summary { display: flex; gap: 14px; color: var(--text-secondary); font-size: 13px; }.summary b { color: var(--text-primary); font-size: 17px; }
.actions { margin-left: auto; display: flex; gap: 8px; }
@media (max-width: 900px) { .toolbar { align-items: flex-end; }.summary { order: 3; width: 100%; }.actions { margin-left: 0; } }
</style>
