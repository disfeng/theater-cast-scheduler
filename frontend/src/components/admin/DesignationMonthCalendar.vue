<template>
  <div class="month-calendar" :aria-label="`${workspace.year}年${workspace.month}月指定与许愿日历`">
    <div v-for="weekday in weekdays" :key="weekday" class="weekday" data-testid="calendar-weekday">{{ weekday }}</div>
    <div v-for="cell in cells" :key="cell.key" class="day-cell" :class="{ muted: !cell.day }">
      <template v-if="cell.day">
        <div class="day-number">{{ cell.day }}日</div>
        <div v-if="cell.performances.length" class="performance-list">
          <button
            v-for="performance in cell.performances"
            :key="performance.id"
            type="button"
            class="performance-card"
            :class="`slot-${slotTone(performance.slot_name)}`"
            :aria-label="`${workspace.month}月${cell.day}日 ${performance.slot_name} 打开审核`"
            @click="$emit('open-performance', performance.id)"
          >
            <span class="performance-head"><strong>{{ performance.slot_name }}</strong><span>{{ shortTime(performance.start_time) }}</span></span>
            <span class="count-row">
              <span>{{ performance.totals.players }} 位玩家</span>
              <span>{{ performance.totals.designations }} 条指定</span>
              <span>{{ performance.totals.wishes }} 条许愿</span>
            </span>
            <span v-if="performance.totals.pending || performance.totals.conflicts" class="state-row">
              <em v-if="performance.totals.pending">{{ performance.totals.pending }} 待处理</em>
              <em v-if="performance.totals.conflicts" class="danger">{{ performance.totals.conflicts }} 冲突</em>
            </span>
          </button>
        </div>
        <div v-else class="empty-day">当日无演出</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { DesignationMonthWorkspace, PerformanceSummary } from "../../features/designation-workspace/types";

const props = defineProps<{ workspace: DesignationMonthWorkspace }>();
defineEmits<{ "open-performance": [performanceId: number] }>();
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
type CalendarCell = { key: string; day: number; performances: PerformanceSummary[] };
const cells = computed(() => {
  const byDate = new Map(props.workspace.days.map(day => [day.date, day.performances]));
  const first = new Date(props.workspace.year, props.workspace.month - 1, 1);
  const leading = (first.getDay() + 6) % 7;
  const count = new Date(props.workspace.year, props.workspace.month, 0).getDate();
  const result: CalendarCell[] = Array.from({ length: leading }, (_, index) => ({ key: `before-${index}`, day: 0, performances: [] }));
  for (let day = 1; day <= count; day += 1) {
    const date = `${props.workspace.year}-${String(props.workspace.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    result.push({ key: date, day, performances: byDate.get(date) ?? [] });
  }
  while (result.length % 7) result.push({ key: `after-${result.length}`, day: 0, performances: [] });
  return result;
});
const shortTime = (value: string) => value.slice(0, 5);
const slotTone = (name: string) => name.includes("早") ? "morning" : name.includes("下午") || name.includes("午") ? "afternoon" : "evening";
</script>

<style scoped>
.month-calendar{display:grid;grid-template-columns:repeat(7,minmax(150px,1fr));overflow:auto;border:1px solid #dfe5ef;border-radius:14px;background:#fff}.weekday{position:sticky;top:0;z-index:2;padding:12px 14px;background:#f7f9fc;color:#64748b;font-size:13px;font-weight:700;text-align:center;border-bottom:1px solid #dfe5ef}.day-cell{min-height:150px;padding:12px;border-right:1px solid #e6eaf1;border-bottom:1px solid #e6eaf1}.day-cell.muted{background:#fafbfc}.day-number{font-weight:700;color:#172033;margin-bottom:10px}.performance-list{display:grid;gap:8px}.performance-card{display:grid;gap:7px;width:100%;padding:10px;border:1px solid #d6dfec;border-left-width:4px;border-radius:9px;background:#fff;color:#253047;text-align:left;cursor:pointer;transition:.18s ease}.performance-card:hover{transform:translateY(-1px);box-shadow:0 6px 16px rgba(30,64,175,.1)}.slot-morning{border-left-color:#48b985;background:#f2fbf6}.slot-afternoon{border-left-color:#198754;background:#eef8f2}.slot-evening{border-left-color:#4b7bec;background:#f3f6ff}.performance-head,.count-row,.state-row{display:flex;justify-content:space-between;gap:7px;flex-wrap:wrap}.performance-head span,.count-row{color:#758198;font-size:12px}.state-row em{font-style:normal;font-size:12px;color:#d18b13}.state-row .danger{color:#e45656}.empty-day{padding-top:22px;color:#b4bdca;font-size:12px;text-align:center}@media(max-width:900px){.month-calendar{grid-template-columns:repeat(7,minmax(132px,1fr))}}
</style>
