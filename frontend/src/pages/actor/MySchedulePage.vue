<template>
  <section class="actor-page">
    <div class="page-heading">
      <div>
        <span class="eyebrow">{{ calendarMode ? "演出日历" : "工作台" }}</span>
        <h1>{{ calendarMode ? monthTitle : greeting }}</h1>
      </div>
      <el-segmented v-model="view" :options="viewOptions" size="small" />
      <el-button size="small" plain @click="exportMonth">导出</el-button>
    </div>

    <div class="month-nav">
      <el-button circle plain aria-label="上个月" @click="moveMonth(-1)">‹</el-button>
      <button class="month-label" @click="resetMonth">{{ monthTitle }}<small>回到本月</small></button>
      <el-button circle plain aria-label="下个月" @click="moveMonth(1)">›</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <section v-if="!calendarMode && unreadRows.length" class="notice-panel">
      <header><div><span>演出通知</span><strong>{{ unreadRows.length }} 条未读</strong></div><small>仅展示已到披露时间的安排</small></header>
      <button v-for="row in unreadRows" :key="`notice-${row.notification_id}`" class="notice-row" @click="readNotice(row)">
        <i></i><div><strong>{{ shortDate(row.performance_date) }} · {{ row.slot_name }}</strong><span>{{ row.theater_name }} · {{ row.role_name }}</span></div><em>查看</em>
      </button>
    </section>

    <template v-if="view === '日历'">
      <div class="weekday"><span v-for="day in weekdays" :key="day">{{ day }}</span></div>
      <div class="calendar-grid">
        <button
          v-for="cell in calendarCells" :key="cell.key" class="date-cell"
          :class="{ muted: !cell.current, active: cell.date === selectedDate, marked: cell.count > 0 }"
          @click="selectedDate = cell.date"
        >
          <span>{{ cell.day }}</span><i v-if="cell.count">{{ cell.count }}</i>
        </button>
      </div>
      <div class="day-section">
        <h2>{{ selectedDateLabel }}</h2>
        <PerformanceCard v-for="row in selectedRows" :key="row.notification_id" :row="row" />
        <div v-if="!loading && !selectedRows.length" class="empty-mini">当天暂无已披露演出</div>
      </div>
    </template>

    <template v-else>
      <div class="list-section">
        <PerformanceCard v-for="row in rows" :key="row.notification_id" :row="row" />
        <el-empty v-if="!loading && !rows.length" description="本月暂无已披露演出" :image-size="74" />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { actorApi, type ActorPerformance } from "../../api/admin";
import { downloadAuthenticated } from "../../api/download";
import { useAuthStore } from "../../auth/store";

const route = useRoute();
const auth = useAuthStore();
const calendarMode = computed(() => route.path.endsWith("/calendar"));
const view = ref(calendarMode.value ? "日历" : "列表");
const viewOptions = ["日历", "列表"];
const month = ref(new Date());
const selectedDate = ref("");
const rows = ref<ActorPerformance[]>([]);
const notifications = ref<ActorPerformance[]>([]);
const loading = ref(false);
const error = ref("");
const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
const greeting = computed(() => "我的排班");
const monthKey = computed(() => `${month.value.getFullYear()}-${String(month.value.getMonth() + 1).padStart(2, "0")}`);
const monthTitle = computed(() => `${month.value.getFullYear()}年${month.value.getMonth() + 1}月`);
const selectedRows = computed(() => rows.value.filter(row => row.performance_date === selectedDate.value));
const unreadRows = computed(() => notifications.value.filter(row => !row.read_at));
const selectedDateLabel = computed(() => selectedDate.value ? `${Number(selectedDate.value.slice(5, 7))}月${Number(selectedDate.value.slice(8))}日安排` : "选择日期");
const calendarCells = computed(() => {
  const year = month.value.getFullYear(); const index = month.value.getMonth();
  const first = new Date(year, index, 1); const offset = (first.getDay() + 6) % 7;
  const start = new Date(year, index, 1 - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start); date.setDate(start.getDate() + i);
    const key = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
    return { key, date: key, day: date.getDate(), current: date.getMonth() === index, count: rows.value.filter(row => row.performance_date === key).length };
  });
});

const PerformanceCard = defineComponent({
  props: { row: { type: Object as () => ActorPerformance, required: true } },
  setup(props) { return () => h("article", { class: "performance-card" }, [
    h("div", { class: "card-time" }, [h("strong", `${Number(props.row.performance_date.slice(5,7))}月${Number(props.row.performance_date.slice(8))}日`), h("span", `${props.row.slot_name} · ${props.row.start_time.slice(0,5)}`)]),
    h("div", { class: "card-main" }, [h("strong", props.row.role_name), h("span", props.row.theater_name), props.row.player_name ? h("span", `对位玩家：${props.row.player_name}`) : null]),
    props.row.designation_label ? h("em", { class: "designation" }, props.row.designation_label) : null,
  ]); } });

async function load() {
  if (!auth.token) return; loading.value = true; error.value = "";
  try {
    const [result, noticeRows] = await Promise.all([actorApi.getCalendar(auth.token, monthKey.value), actorApi.getNotifications(auth.token, true)]); rows.value = result.performances; notifications.value = noticeRows;
    const first = rows.value[0]?.performance_date;
    if (!selectedDate.value.startsWith(monthKey.value)) selectedDate.value = first || `${monthKey.value}-01`;
  } catch (err: any) { error.value = err.message === "password_change_required" ? "请先修改初始密码" : (err.message || "排班加载失败"); }
  finally { loading.value = false; }
}
const shortDate=(value:string)=>`${Number(value.slice(5,7))}月${Number(value.slice(8))}日`;
async function readNotice(row:ActorPerformance){if(!auth.token)return;await actorApi.markNotificationRead(auth.token,row.notification_id);row.read_at=new Date().toISOString();selectedDate.value=row.performance_date;month.value=new Date(`${row.performance_date}T00:00:00`);view.value="日历"}
function moveMonth(delta: number) { month.value = new Date(month.value.getFullYear(), month.value.getMonth() + delta, 1); }
function resetMonth() { month.value = new Date(); }
async function exportMonth() {
  if (!auth.token) return;
  try { await downloadAuthenticated(`/actor/me/calendar/export?month=${monthKey.value}`, auth.token, `我的班次-${monthKey.value}.csv`); }
  catch (err: any) { error.value = err.message || "导出失败"; }
}
watch(monthKey, load); watch(calendarMode, value => { view.value = value ? "日历" : "列表"; });
onMounted(load);
</script>

<style scoped>
.actor-page { color: #182236; }
.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.eyebrow { color: #2f6fed; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h1 { margin: 5px 0 0; font-size: 27px; }
.month-nav { display: flex; align-items: center; justify-content: space-between; padding: 13px 14px; margin-bottom: 16px; background: #fff; border: 1px solid #e1e8f2; border-radius: 16px; }
.month-label { border: 0; background: transparent; color: #182236; font-weight: 700; font-size: 16px; }
.month-label small { display: block; color: #98a2b3; font-size: 10px; font-weight: 400; margin-top: 2px; }
.weekday, .calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); }
.weekday { color: #8490a3; font-size: 11px; text-align: center; padding: 7px 0; }
.calendar-grid { overflow: hidden; background: #fff; border: 1px solid #e1e8f2; border-radius: 16px; }
.date-cell { position: relative; min-height: 51px; border: 0; border-right: 1px solid #edf0f5; border-bottom: 1px solid #edf0f5; background: #fff; color: #344054; }
.date-cell.muted { color: #c4cad4; background: #fafbfc; }.date-cell.active { color: #fff; background: #2f6fed; }.date-cell.marked:not(.active)::after { content:""; position:absolute; bottom:7px; left:50%; width:4px; height:4px; border-radius:50%; background:#2f6fed; }
.date-cell i { position: absolute; top: 4px; right: 5px; font-style: normal; font-size: 9px; }
.day-section, .list-section { margin-top: 18px; }.day-section h2 { margin: 0 0 10px; font-size: 16px; }
:deep(.performance-card) { position: relative; display: grid; grid-template-columns: 82px 1fr; gap: 12px; padding: 15px; margin-bottom: 10px; background: #fff; border: 1px solid #e1e8f2; border-radius: 16px; box-shadow: 0 5px 16px rgba(38,53,79,.045); }
:deep(.card-time), :deep(.card-main) { display: flex; flex-direction: column; gap: 4px; }:deep(.card-time span), :deep(.card-main span) { color: #7b8799; font-size: 12px; }:deep(.card-main strong) { font-size: 16px; }
:deep(.designation) { position: absolute; right: 12px; top: 12px; padding: 3px 7px; border-radius: 999px; background: #fff3dc; color: #b76300; font-size: 10px; font-style: normal; font-weight: 700; }
.empty-mini { padding: 28px; text-align: center; color: #98a2b3; background: #fff; border: 1px dashed #dbe2ec; border-radius: 16px; }
.notice-panel{padding:15px;margin-bottom:16px;background:linear-gradient(145deg,#fff,#f8fbff);border:1px solid #dbe6f6;border-radius:18px}.notice-panel header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:8px}.notice-panel header div{display:flex;align-items:center;gap:8px}.notice-panel header span{font-size:15px;font-weight:700}.notice-panel header strong{padding:2px 7px;border-radius:999px;background:#eaf2ff;color:#2f6fed;font-size:10px}.notice-panel header small{color:#98a2b3;font-size:10px}.notice-row{display:grid;grid-template-columns:7px 1fr auto;align-items:center;gap:10px;width:100%;padding:11px 3px;border:0;border-top:1px solid #edf1f6;background:transparent;text-align:left}.notice-row i{width:7px;height:7px;border-radius:50%;background:#2f6fed}.notice-row div{display:flex;flex-direction:column;gap:3px}.notice-row strong{color:#182236;font-size:13px}.notice-row span{color:#7b8799;font-size:11px}.notice-row em{color:#2f6fed;font-size:11px;font-style:normal;font-weight:600}
</style>
