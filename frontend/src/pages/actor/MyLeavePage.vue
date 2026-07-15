<template>
  <section class="page-container">
    <PageHeader title="我的请假" description="按月提交整天请假，查看审核状态。" />

    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <div class="panel" style="margin: 0;">
      <h3>提交新请假申请</h3>
      <form @submit.prevent="handleSubmit" style="display: grid; gap: 16px; margin-top: 10px;">
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <label for="leave-dates-input">请假日期</label>
          <input
            id="leave-dates-input"
            aria-label="请假日期"
            v-model="datesInput"
            placeholder="例如：2026-06-16, 2026-06-17"
            required
            style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
          />
        </div>

        <div style="display: flex; flex-direction: column; gap: 6px;">
          <label for="leave-note-input">备注</label>
          <input
            id="leave-note-input"
            aria-label="备注"
            v-model="noteInput"
            placeholder="例如：家里有急事 / 生病"
            style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
          />
        </div>

        <button type="submit" style="margin-top: 8px; padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">提交请假</button>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "../../auth/store";
import { actorApi } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";

const authStore = useAuthStore();

const datesInput = ref("");
const noteInput = ref("");
const error = ref<string | null>(null);
const success = ref<string | null>(null);

const handleSubmit = async () => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    const dates = datesInput.value
      .split(/[\n,]/)
      .map((d) => d.trim())
      .filter(Boolean);
    await actorApi.submitLeave(authStore.token, {
      dates,
      note: noteInput.value || null
    });
    datesInput.value = "";
    noteInput.value = "";
    success.value = "请假申请提交成功！";
  } catch (err: any) {
    error.value = err.message || "提交请假申请失败";
  }
};
</script>
