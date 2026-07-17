<template>
  <el-card shadow="never" data-testid="reconciliation-panel">
    <template #header><strong>权益与流水核对</strong></template>
    <el-radio-group v-model="expiry" aria-label="到期筛选" :disabled="loading" @change="loadSummary">
      <el-radio-button value="">全部</el-radio-button>
      <el-radio-button value="expired">已过期</el-radio-button>
      <el-radio-button value="expires_within_7_days">7 天内到期</el-radio-button>
      <el-radio-button value="expires_within_30_days">30 天内到期</el-radio-button>
    </el-radio-group>
    <div v-if="loading" role="status">正在加载核对结果…</div>
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-else-if="summary">
      <el-space wrap>
        <el-tag>筛选范围 {{ total(summary.filtered_totals) }} 张</el-tag>
        <el-tag type="info">全局 {{ total(summary.global_totals) }} 张</el-tag>
        <el-tag :type="summary.anomaly_count ? 'danger' : 'success'">异常 {{ summary.anomaly_count }}</el-tag>
      </el-space>
      <el-table :data="summary.rows" size="small">
        <el-table-column prop="item_type" label="类型" />
        <el-table-column prop="source_month" label="来源月份" />
        <el-table-column prop="source_label" label="来源" />
        <el-table-column prop="player_name" label="玩家" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="item_count" label="数量" />
        <el-table-column label="下钻">
          <template #default="scope">
            <el-button size="small" @click="openDrill('items', scope.row.drill_down_filter)">道具</el-button>
            <el-button size="small" @click="openDrill('ledgers', scope.row.drill_down_filter)">流水</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button :disabled="!summary.anomaly_count" @click="openDrill('anomalies', {})">查看异常</el-button>
    </template>
    <el-drawer v-model="drawer" title="核对明细" size="min(720px, 92vw)">
      <div v-if="drillLoading" role="status">正在加载明细…</div>
      <el-alert v-else-if="drillError" :title="drillError" type="error" :closable="false" />
      <template v-else-if="drill">
        <p>共 {{ drill.total }} 条</p>
        <pre v-for="record in drill.records" :key="record.id ?? JSON.stringify(record)">{{ record }}</pre>
        <el-button v-if="drill.next_cursor !== null" @click="loadMore">加载更多</el-button>
      </template>
    </el-drawer>
  </el-card>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { adminApi } from "../../api/admin";
import type { EntitlementReconciliation, ReconciliationDrill } from "../../api/admin";
import { useAuthStore } from "../../auth/store";

const auth = useAuthStore();
const expiry = ref("");
const loading = ref(false), error = ref("");
const summary = ref<EntitlementReconciliation | null>(null);
const drawer = ref(false), drillLoading = ref(false), drillError = ref("");
const drill = ref<ReconciliationDrill | null>(null);
const currentKind = ref<"items" | "ledgers" | "anomalies">("items");
const currentFilters = ref<Record<string, string | number>>({});
const total = (values: Record<string, number>) => Object.values(values).reduce((sum, value) => sum + value, 0);
async function loadSummary() {
  if (!auth.token) { error.value = "请先登录后查看核对结果"; return; }
  loading.value = true; error.value = "";
  try { summary.value = await adminApi.getEntitlementReconciliation(auth.token, expiry.value || undefined); }
  catch (e: any) { summary.value = null; error.value = e.message; }
  finally { loading.value = false; }
}
async function openDrill(kind: typeof currentKind.value, filters: Record<string, string | number>) {
  currentKind.value = kind; currentFilters.value = filters; drawer.value = true;
  drillLoading.value = true; drillError.value = "";
  try { drill.value = await adminApi.getEntitlementReconciliationDrill(auth.token!, kind, expiry.value || undefined, filters); }
  catch (e: any) { drill.value = null; drillError.value = e.message; }
  finally { drillLoading.value = false; }
}
async function loadMore() {
  if (!drill.value?.next_cursor) return;
  const next = await adminApi.getEntitlementReconciliationDrill(auth.token!, currentKind.value,
    expiry.value || undefined, currentFilters.value, drill.value.next_cursor);
  drill.value = { ...next, records: [...drill.value.records, ...next.records] };
}
onMounted(loadSummary);
</script>
