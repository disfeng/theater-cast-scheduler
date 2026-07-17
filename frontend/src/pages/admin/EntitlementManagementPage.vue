<template>
  <section class="page-container">
    <PageHeader title="权益管理" description="管理月度权益发放、玩家权益背包与权益流水核对。" />

    <el-tabs v-model="activeTab" class="entitlement-tabs" @tab-change="syncTabQuery">
      <el-tab-pane label="月度发放" name="grants" lazy>
        <GrantBatchTab />
      </el-tab-pane>
      <el-tab-pane label="权益背包" name="inventory" lazy>
        <PlayerInventoryTab />
      </el-tab-pane>
      <el-tab-pane label="权益流水核对" name="reconciliation" lazy>
        <ReconciliationPanel />
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import GrantBatchTab from "../../components/admin/GrantBatchTab.vue";
import PlayerInventoryTab from "../../components/admin/PlayerInventoryTab.vue";
import ReconciliationPanel from "../../components/admin/ReconciliationPanel.vue";
import PageHeader from "../../components/PageHeader.vue";

const route = useRoute();
const router = useRouter();
const allowedTabs = new Set(["grants", "inventory", "reconciliation"]);
const initialTab = typeof route.query.tab === "string" && allowedTabs.has(route.query.tab)
  ? route.query.tab
  : "grants";
const activeTab = ref(initialTab);

watch(
  () => route.query.tab,
  (tab) => {
    if (typeof tab === "string" && allowedTabs.has(tab)) activeTab.value = tab;
  },
);

function syncTabQuery(tab: string | number) {
  const next = String(tab);
  if (!allowedTabs.has(next) || route.query.tab === next) return;
  void router.replace({ query: { ...route.query, tab: next } });
}
</script>

<style scoped>
.entitlement-tabs :deep(.el-tabs__content) { padding-top: 8px; }
</style>
