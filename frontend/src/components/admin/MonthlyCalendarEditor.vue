<template>
  <div class="calendar-editor">
    <div class="calendar-legend" aria-label="日历状态图例">
      <span><i class="legend-mark persisted" />已保存</span>
      <span><i class="legend-mark closed" />闭店</span>
      <span><i class="legend-mark template" />模板待保存</span>
    </div>
    <div class="calendar-scroll">
      <div class="calendar-grid">
      <div v-for="label in WEEK_LABELS" :key="label" class="weekday">{{ label }}</div>
      <div
        v-for="cell in cells"
        :key="cell.key"
        class="day-cell"
        :class="{
          filler: !cell.date,
          'is-closed': cell.date && !modelValue[cell.date]?.length,
          'is-persisted': cell.date && !!modelValue[cell.date]?.length && persistedDates.includes(cell.date),
        }"
      >
        <template v-if="cell.date">
          <div class="day-header">
            <strong>{{ cell.day }}</strong>
            <el-tag v-if="!(modelValue[cell.date]?.length)" class="closed-tag" type="danger" size="small">闭店</el-tag>
          </div>
          <div class="slot-list">
            <button
              v-for="slot in activeSlots"
              :key="slot.id"
              type="button"
              class="slot-toggle"
              :class="{ active: modelValue[cell.date]?.includes(slot.id) }"
              :aria-label="`${month}月${cell.day}日 ${modelValue[cell.date]?.includes(slot.id) ? '关闭' : '开启'}${slot.name}`"
              @click="toggle(cell.date, slot.id)"
            >
              <span>{{ slot.name }}</span><small>{{ slot.start_time.slice(0, 5) }}</small>
            </button>
          </div>
          <button
            v-if="modelValue[cell.date]?.length"
            type="button"
            class="day-action danger"
            :aria-label="`${month}月${cell.day}日 设为闭店`"
            @click="closeDay(cell.date)"
          >设为闭店</button>
          <button
            v-else
            type="button"
            class="day-action"
            :aria-label="`${month}月${cell.day}日 按模板恢复`"
            @click="restoreDay(cell.date, cell.weekday)"
          >按模板恢复</button>
        </template>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { TheaterSlot, WeeklyTemplate } from "../../api/admin";
import { formatDate, toggleDraftSlot, type MonthlyCalendarDraft } from "../../features/monthly-plan/calendarDraft";

const props = defineProps<{
  year: number;
  month: number;
  slots: TheaterSlot[];
  weeklyTemplate: WeeklyTemplate;
  modelValue: MonthlyCalendarDraft;
  persistedDates: string[];
}>();
const emit = defineEmits<{ (event: "update:modelValue", value: MonthlyCalendarDraft): void; (event: "dirty"): void }>();
const WEEK_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const WEEKDAY_KEYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const activeSlots = computed(() => [...props.slots].filter((slot) => slot.is_active).sort((a, b) => a.sort_order - b.sort_order));
const cells = computed(() => {
  const leading = (new Date(props.year, props.month - 1, 1).getDay() + 6) % 7;
  const values = Array.from({ length: leading }, (_, index) => ({ key: `before-${index}`, day: 0, date: "", weekday: "" }));
  const days = new Date(props.year, props.month, 0).getDate();
  for (let day = 1; day <= days; day += 1) {
    const value = new Date(props.year, props.month - 1, day);
    values.push({ key: formatDate(props.year, props.month, day), day, date: formatDate(props.year, props.month, day), weekday: WEEKDAY_KEYS[value.getDay()] });
  }
  while (values.length % 7) values.push({ key: `after-${values.length}`, day: 0, date: "", weekday: "" });
  return values;
});
function update(value: MonthlyCalendarDraft) { emit("update:modelValue", value); emit("dirty"); }
function toggle(date: string, slotId: number) { update(toggleDraftSlot(props.modelValue, date, slotId)); }
function closeDay(date: string) { update({ ...props.modelValue, [date]: [] }); }
function restoreDay(date: string, weekday: string) { update({ ...props.modelValue, [date]: [...(props.weeklyTemplate[weekday] || [])] }); }
</script>

<style scoped>
.calendar-editor { display: grid; gap: 10px; }
.calendar-legend { display: flex; justify-content: flex-end; align-items: center; gap: 18px; color: #7b8494; font-size: 12px; }
.calendar-legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend-mark { width: 9px; height: 9px; border-radius: 50%; border: 1px solid transparent; }
.legend-mark.persisted { background: #67c23a; box-shadow: 0 0 0 3px #edf8e8; }
.legend-mark.closed { background: #fef0f0; border-color: #f56c6c; }
.legend-mark.template { background: #fff; border-color: #b8c1cf; }
.calendar-scroll { overflow-x: auto; border: 1px solid var(--panel-border); border-radius: 12px; background: #fff; }
.calendar-grid { display: grid; grid-template-columns: repeat(7, minmax(140px, 1fr)); min-width: 980px; }
.weekday { padding: 10px; text-align: center; color: #667085; font-size: 13px; font-weight: 600; background: #f7f9fc; border-right: 1px solid var(--panel-border); border-bottom: 1px solid var(--panel-border); }
.day-cell { min-height: 160px; padding: 10px 10px 10px 13px; border-right: 1px solid var(--panel-border); border-bottom: 1px solid var(--panel-border); transition: background-color .18s ease, box-shadow .18s ease; }
.day-cell.filler { background: #fafbfc; }
.day-cell.is-closed { background: #f3f4f6; }
.day-cell.is-persisted { background: linear-gradient(180deg, #f1faf4 0, #fff 48px); box-shadow: inset 4px 0 0 #67c23a; }
.closed-tag { --el-tag-bg-color: #fef0f0; --el-tag-border-color: #fbc4c4; --el-tag-text-color: #c45656; }
.day-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.slot-list { display: grid; gap: 5px; }
.slot-toggle { display: flex; justify-content: space-between; gap: 6px; padding: 5px 7px; border-radius: 6px; border: 1px solid #e2e6ed; background: #fafbfc; color: #8a94a5; cursor: pointer; font-size: 12px; transition: border-color .15s ease, background-color .15s ease, color .15s ease; }
.slot-toggle.active { color: #2458a6; border-color: #9dc1fa; background: #edf4ff; }
.slot-toggle:hover { border-color: #b8c5d8; color: #526176; }
.slot-toggle small { opacity: .8; }
.day-action { margin-top: 8px; padding: 0; border: 0; background: transparent; color: #667085; font-size: 11px; cursor: pointer; }
.day-action.danger { color: #8a94a5; }
.day-action.danger:hover, .day-action.danger:focus-visible { color: #d84c4c; }
</style>
