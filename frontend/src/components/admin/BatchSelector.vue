<template>
  <div class="panel" style="margin: 0;">
    <h3>周批次管理</h3>
    <form @submit.prevent="$emit('submit')" style="display: grid; gap: 16px; margin-top: 10px;">
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label for="theater-select">选择剧场</label>
        <select
          id="theater-select"
          aria-label="选择剧场"
          :value="modelValue.theaterId"
          @change="$emit('update:modelValue', { ...modelValue, theaterId: ($event.target as HTMLSelectElement).value })"
          required
          style="padding: 8px 12px; border-radius: 6px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: var(--text-primary);"
        >
          <option value="">-- 请选择剧场 --</option>
          <option v-for="t in theaters" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label for="week-start-input">周一日期</label>
        <input
          id="week-start-input"
          aria-label="周一日期"
          type="date"
          :value="modelValue.weekStart"
          @input="$emit('update:modelValue', { ...modelValue, weekStart: ($event.target as HTMLInputElement).value })"
          required
          style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
        />
      </div>

      <button type="submit" style="padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">创建/打开批次</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { Theater } from "../../api/admin";

defineProps<{
  modelValue: { theaterId: string; weekStart: string };
  theaters: Theater[];
}>();

defineEmits<{
  (e: "update:modelValue", val: { theaterId: string; weekStart: string }): void;
  (e: "submit"): void;
}>();
</script>
