<template>
  <section class="page-container">
    <PageHeader title="指定与许愿" description="按演出场次管理玩家登记、指定申请与许愿信息。" />

    <section class="calendar-toolbar">
      <div class="toolbar-field">
        <span>选择剧场</span>
        <el-select v-model="selectedTheaterId" aria-label="指定与许愿剧场" placeholder="请选择剧场">
          <el-option v-for="theater in theaters" :key="theater.id" :label="theater.name" :value="theater.id" />
        </el-select>
      </div>
      <div class="month-navigation">
        <el-button circle aria-label="上个月" @click="moveMonth(-1)"><el-icon><ArrowLeft /></el-icon></el-button>
        <strong>{{ selectedYear }} 年 {{ selectedMonth }} 月</strong>
        <el-button circle aria-label="下个月" @click="moveMonth(1)"><el-icon><ArrowRight /></el-icon></el-button>
      </div>
      <div v-if="monthWorkspace" class="month-summary">
        <span>{{ monthWorkspace.totals.players }} 位玩家</span>
        <span>{{ monthWorkspace.totals.designations }} 条指定</span>
        <span>{{ monthWorkspace.totals.wishes }} 条许愿</span>
        <span class="pending">{{ monthWorkspace.totals.pending }} 待处理</span>
        <span class="conflict">{{ monthWorkspace.totals.conflicts }} 冲突</span>
      </div>
    </section>

    <el-alert v-if="calendarError" :title="calendarError" type="error" :closable="false" show-icon />
    <div v-loading="calendarLoading" class="calendar-content">
      <DesignationMonthCalendar v-if="monthWorkspace" :workspace="monthWorkspace" @open-performance="openPerformance" />
      <el-empty v-else-if="!calendarLoading && !calendarError" description="请选择剧场查看月度场次" />
    </div>

    <PerformanceReviewDrawer
      v-model="drawerVisible"
      :workspace="performanceWorkspace"
      :loading="drawerLoading"
      :error="drawerError"
      :initial-tab="String(route.query.review_tab || 'players')"
      @reject-designation="rejectDesignation"
      @reject-wish="rejectWish"
      @accept-wish="acceptWish"
      @changed="refreshReviewWorkspace"
      @tab-change="persistReviewTab"
    />
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight } from "@element-plus/icons-vue";
import { adminApi, type Theater } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import PageHeader from "../../components/PageHeader.vue";
import DesignationMonthCalendar from "../../components/admin/DesignationMonthCalendar.vue";
import PerformanceReviewDrawer from "../../components/admin/PerformanceReviewDrawer.vue";
import type { DesignationMonthWorkspace, PerformanceWorkspace } from "../../features/designation-workspace/types";

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const today = new Date();
const theaters = ref<Theater[]>([]);
const selectedTheaterId = ref(Number(route.query.theater_id) || 0);
const selectedYear = ref(Number(route.query.year) || today.getFullYear());
const selectedMonth = ref(Number(route.query.month) || today.getMonth() + 1);
const monthWorkspace = ref<DesignationMonthWorkspace | null>(null);
const calendarLoading = ref(false);
const calendarError = ref<string | null>(null);
const drawerVisible = ref(false);
const drawerLoading = ref(false);
const drawerError = ref<string | null>(null);
const performanceWorkspace = ref<PerformanceWorkspace | null>(null);

onMounted(async () => {
  if (!authStore.token) return;
  try {
    theaters.value = await adminApi.getTheaters(authStore.token);
    if (!selectedTheaterId.value && theaters.value.length) selectedTheaterId.value = theaters.value[0].id;
  } catch (error: any) {
    calendarError.value = error.message || "加载剧场失败";
  }
});

watch([selectedTheaterId, selectedYear, selectedMonth], async ([theaterId, year, month]) => {
  if (!authStore.token || !theaterId) return;
  calendarLoading.value = true;
  calendarError.value = null;
  try {
    const workspace = await adminApi.getDesignationMonthWorkspace(authStore.token, theaterId, year, month);
    if (!workspace?.totals || !Array.isArray(workspace.days)) throw new Error("月度工作台返回数据格式错误");
    monthWorkspace.value = workspace;
    await router.replace({ query: { ...route.query, theater_id: String(theaterId), year: String(year), month: String(month) } });
  } catch (error: any) {
    monthWorkspace.value = null;
    calendarError.value = error.message || "加载月度工作台失败";
  } finally {
    calendarLoading.value = false;
  }
}, { immediate: true });

watch(drawerVisible, visible => {
  if (!visible && route.query.performance_id) {
    const query = { ...route.query };
    delete query.performance_id;
    delete query.review_tab;
    void router.replace({ query });
  }
});

watch(() => route.query.performance_id, (value, previous) => {
  const performanceId = Number(value);
  if (performanceId && value !== previous && performanceWorkspace.value?.performance.id !== performanceId) {
    void openPerformance(performanceId, true);
  }
}, { immediate: true });

function moveMonth(offset: number) {
  const target = new Date(selectedYear.value, selectedMonth.value - 1 + offset, 1);
  selectedYear.value = target.getFullYear();
  selectedMonth.value = target.getMonth() + 1;
}

async function openPerformance(performanceId: number, preserveTab = false) {
  if (!authStore.token) return;
  drawerVisible.value = true;
  drawerLoading.value = true;
  drawerError.value = null;
  performanceWorkspace.value = null;
  const reviewTab = preserveTab ? String(route.query.review_tab || "players") : "players";
  if (String(route.query.performance_id || "") !== String(performanceId) || route.query.review_tab !== reviewTab) {
    void router.replace({ query: { ...route.query, performance_id: String(performanceId), review_tab: reviewTab } });
  }
  try {
    performanceWorkspace.value = await adminApi.getPerformanceReviewWorkspace(authStore.token, performanceId);
  } catch (error: any) {
    drawerError.value = error.message || "加载场次审核信息失败";
  } finally {
    drawerLoading.value = false;
  }
}

async function refreshReviewWorkspace() {
  const performanceId = performanceWorkspace.value?.performance.id;
  if (!authStore.token || !performanceId) return;
  performanceWorkspace.value = await adminApi.getPerformanceReviewWorkspace(authStore.token, performanceId);
  monthWorkspace.value = await adminApi.getDesignationMonthWorkspace(authStore.token, selectedTheaterId.value, selectedYear.value, selectedMonth.value);
}

function persistReviewTab(tab: string) {
  if (route.query.review_tab !== tab) void router.replace({ query: { ...route.query, review_tab: tab } });
}

async function rejectDesignation(id: number, reason: string) {
  const row = performanceWorkspace.value?.designations.find(item => item.id === id);
  if (!authStore.token || !row) return;
  await runDrawerAction("拒绝指定失败", () => adminApi.cancelDesignation(authStore.token!, row, reason));
}

async function rejectWish(id: number, reason: string) {
  const row = performanceWorkspace.value?.wishes.find(item => item.id === id);
  if (!authStore.token || !row) return;
  await runDrawerAction("拒绝许愿失败", () => adminApi.cancelWish(authStore.token!, row, reason));
}

async function acceptWish(id: number) {
  const row = performanceWorkspace.value?.wishes.find(item => item.id === id);
  if (!authStore.token || !row) return;
  await runDrawerAction("接受许愿失败", () => adminApi.acceptWish(authStore.token!, row));
}

async function runDrawerAction(fallback: string, action: () => Promise<unknown>) {
  drawerLoading.value = true;
  drawerError.value = null;
  try {
    await action();
    await refreshReviewWorkspace();
  } catch (error: any) {
    drawerError.value = error.message || fallback;
  } finally {
    drawerLoading.value = false;
  }
}
</script>

<style scoped>
.calendar-toolbar{display:flex;align-items:center;gap:22px;flex-wrap:wrap;padding:18px 20px;margin-bottom:18px;border:1px solid #dfe5ef;border-radius:12px;background:#fff}.toolbar-field{display:flex;align-items:center;gap:10px;color:#64748b}.toolbar-field :deep(.el-select){width:240px}.month-navigation{display:flex;align-items:center;gap:12px;padding-left:20px;border-left:1px solid #e4e9f1}.month-navigation strong{min-width:112px;text-align:center;color:#172033}.month-summary{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-left:auto}.month-summary span{padding:6px 10px;border-radius:999px;background:#f1f5f9;color:#64748b;font-size:13px}.month-summary .pending{background:#fff7e6;color:#b7791f}.month-summary .conflict{background:#fff0f0;color:#d84f4f}.calendar-content{min-height:260px}@media(max-width:900px){.month-navigation{padding-left:0;border-left:0}.month-summary{width:100%;margin-left:0}}
</style>
