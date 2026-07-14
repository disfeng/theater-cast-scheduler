<template>
  <section class="page-container">
    <PageHeader
      title="周排班"
      description="锁定关键卡司，生成补排，查看指定失败和硬规则冲突。"
    />
    <div class="panel schedule-placeholder">
      <div>
        <strong>排班表区域</strong>
        <p>用于组织就绪批次、排班预览与规则冲突复核。</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import PageHeader from "../../components/PageHeader.vue";
</script>

<style scoped>
.schedule-placeholder {
  min-height: 280px;
  display: grid;
  place-items: center;
  text-align: center;
}
.schedule-placeholder p { margin-top: 8px; color: var(--text-secondary); }
</style>
