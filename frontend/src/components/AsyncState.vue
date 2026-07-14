<template>
  <div>
    <div v-if="loading" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 0; gap: 12px;">
      <el-icon class="is-loading" :size="32" style="color: var(--primary);"><Loading /></el-icon>
      <span style="color: var(--text-secondary); font-size: 14px;">加载中...</span>
    </div>
    
    <div v-else-if="error" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 0; gap: 16px;">
      <span style="color: var(--danger); font-size: 14px;">{{ error }}</span>
      <el-button type="primary" size="small" @click="$emit('retry')">重试</el-button>
    </div>
    
    <div v-else-if="empty" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 0; gap: 12px;">
      <el-empty :description="emptyText || '暂无数据'" />
    </div>
    
    <div v-else>
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loading } from "@element-plus/icons-vue";

defineProps<{
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  emptyText?: string;
}>();

defineEmits<{
  (e: "retry"): void;
}>();
</script>
