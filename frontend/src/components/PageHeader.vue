<template>
  <div style="margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px;">
    <div>
      <h2 style="font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px;">{{ title }}</h2>
      <p v-if="description" style="font-size: 14px; color: var(--text-secondary);">{{ description }}</p>
    </div>
    <div style="display: flex; gap: 10px; align-items: center;">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>
