<template>
  <div class="page-header" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px;">
    <div class="page-header__copy" style="display: grid; gap: 8px;">
      <h2 style="font-size: 24px; font-weight: 700; color: var(--text-primary); margin: 0;">{{ title }}</h2>
      <p v-if="description" style="font-size: 14px; color: var(--text-secondary); margin: 0;">{{ description }}</p>
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
