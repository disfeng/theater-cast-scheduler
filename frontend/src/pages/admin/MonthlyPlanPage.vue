<template>
  <section style="max-width: 1200px; margin: 0 auto;">
    <PageHeader title="月度计划" description="在此生成并微调月度演出排班表，支持按模板批量生成，也可以单独添加或删除特定场次。" />
    
    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px; align-items: start;">
      
      <!-- Left Column: Actions Form -->
      <div style="display: flex; flex-direction: column; gap: 30px;">
        
        <!-- Batch Generation Panel -->
        <div class="panel" style="margin: 0;">
          <h3>批量生成计划</h3>
          <div style="display: grid; gap: 16px; margin-top: 10px;">
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="theater-select">选择剧场</label>
              <select id="theater-select" aria-label="选择剧场" v-model="theaterId" style="padding: 8px 12px; border-radius: 6px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;">
                <option value="">-- 请选择剧场 --</option>
                <option v-for="t in theaters" :key="t.id" :value="t.id">{{ t.name }}</option>
              </select>
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="year-input">年份</label>
              <input id="year-input" aria-label="年份" type="number" v-model.number="year" style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;" />
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="month-input">月份</label>
              <input id="month-input" aria-label="月份" type="number" min="1" max="12" v-model.number="month" style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;" />
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="closed-dates-area">闭店日期</label>
              <textarea id="closed-dates-area" aria-label="闭店日期" placeholder="YYYY-MM-DD，多日期用逗号或换行分隔" v-model="closedDates" style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff; min-height: 80px;" />
            </div>
            <button type="button" style="padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;" @click="handleGenerate">生成月度计划</button>
          </div>
        </div>

        <!-- Add Custom Single Performance Panel -->
        <div class="panel" style="margin: 0;">
          <h3>添加单个场次</h3>
          <form @submit.prevent="handleAddCustomPerformance" style="display: grid; gap: 16px; margin-top: 10px;">
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="custom-date-input">选择日期</label>
              <input
                id="custom-date-input"
                aria-label="选择日期"
                type="date"
                v-model="customDate"
                required
                style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
              />
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="custom-slot-select">场次选择</label>
              <select
                id="custom-slot-select"
                aria-label="场次选择"
                v-model="customSlot"
                style="padding: 8px 12px; border-radius: 6px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
              >
                <option value="early">下午场 (Early)</option>
                <option value="late">晚场 (Late)</option>
              </select>
            </div>
            <button type="submit" style="padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">确认添加</button>
          </form>
        </div>

      </div>

      <!-- Right Column: Performance list grid -->
      <div class="panel" style="margin: 0;">
        <h3>本月场次列表 ({{ performances.length }})</h3>
        <p v-if="performances.length === 0" style="color: var(--text-secondary); margin-top: 10px;">暂无该月份演出场次。</p>
        <div v-else style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-top: 12px;">
          <div
            v-for="performance in performances"
            :key="performance.id"
            class="panel"
            style="padding: 16px; margin: 0; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--panel-border); display: flex; flex-direction: column; justify-content: space-between;"
          >
            <div>
              <div style="font-weight: 600; font-size: 15px; color: #fff; margin-bottom: 8px;">
                {{ performance.performance_date }}
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="badge badge-success">
                  {{ performance.slot === "early" ? "下午场" : performance.slot === "late" ? "晚场" : performance.slot }}
                </span>
                <span style="font-size: 11px; color: var(--text-secondary);">
                  {{ performance.status === "draft" ? "草稿" : "已发布" }}
                </span>
              </div>
            </div>
            
            <!-- Delete Option -->
            <button
              type="button"
              @click="handleDeletePerformance(performance.id)"
              style="margin-top: 16px; background: rgba(220, 63, 69, 0.1); border: 1px solid rgba(220, 63, 69, 0.3); color: #bd2f35; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; text-align: center;"
            >
              删除场次
            </button>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, Performance, Theater } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";

const authStore = useAuthStore();

const theaters = ref<Theater[]>([]);
const performances = ref<Performance[]>([]);

const theaterId = ref<number | "">("");
const year = ref(2026);
const month = ref(6);
const closedDates = ref("");

const customDate = ref("2026-06-01");
const customSlot = ref("early");

const error = ref<string | null>(null);
const success = ref<string | null>(null);

const refreshTheaters = async () => {
  if (!authStore.token) return;
  try {
    const res = await adminApi.getTheaters(authStore.token);
    theaters.value = res;
    if (res.length > 0 && theaterId.value === "") {
      theaterId.value = res[0].id;
    }
  } catch (err: any) {
    error.value = err.message;
  }
};

const loadPerformances = async () => {
  if (!authStore.token || !theaterId.value) return;
  try {
    const res = await adminApi.getPerformances(authStore.token, Number(theaterId.value), year.value, month.value);
    performances.value = res;
  } catch (err: any) {
    error.value = err.message;
  }
};

onMounted(async () => {
  await refreshTheaters();
  await loadPerformances();
});

watch([theaterId, year, month], () => {
  loadPerformances();
});

watch([year, month], () => {
  customDate.value = `${year.value}-${String(month.value).padStart(2, "0")}-01`;
});

const handleGenerate = async () => {
  if (!authStore.token || !theaterId.value) return;
  error.value = null;
  success.value = null;
  try {
    const dates = closedDates.value
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    const res = await adminApi.generateMonthlyPlan(authStore.token, {
      theater_id: Number(theaterId.value),
      year: year.value,
      month: month.value,
      closed_dates: dates,
    });
    performances.value = res;
    success.value = "批量生成月度计划成功！";
  } catch (err: any) {
    error.value = err.message || "生成失败";
  }
};

const handleAddCustomPerformance = async () => {
  if (!authStore.token || !theaterId.value) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.createPerformance(authStore.token, {
      theater_id: Number(theaterId.value),
      performance_date: customDate.value,
      slot: customSlot.value,
    });
    success.value = "自定义场次添加成功！";
    await loadPerformances();
  } catch (err: any) {
    error.value = err.message || "添加场次失败";
  }
};

const handleDeletePerformance = async (perfId: number) => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  if (!window.confirm("确定要删除该场次吗？")) return;
  try {
    await adminApi.deletePerformance(authStore.token, perfId);
    success.value = "场次删除成功！";
    await loadPerformances();
  } catch (err: any) {
    error.value = err.message || "删除场次失败";
  }
};
</script>
