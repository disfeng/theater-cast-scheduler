<template>
  <section style="max-width: 1000px; margin: 0 auto;">
    <PageHeader title="请假审核" description="审批演员的请假申请，批准后的请假将在排班算法中作为硬约束考虑。" />

    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <div class="panel" style="margin: 0;">
      <h3>待审核申请 ({{ requests.length }})</h3>
      <p v-if="requests.length === 0" style="color: var(--text-secondary); margin-top: 10px;">当前暂无请假申请。</p>
      
      <div v-else style="overflow-x: auto; margin-top: 16px;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
          <thead>
            <tr style="border-bottom: 1px solid var(--panel-border); color: var(--text-secondary);">
              <th style="padding: 12px;">演员</th>
              <th style="padding: 12px;">日期</th>
              <th style="padding: 12px;">当前状态</th>
              <th style="padding: 12px;">备注</th>
              <th style="padding: 12px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="request in requests" :key="request.id" style="border-bottom: 1px solid var(--panel-border);">
              <td style="padding: 12px; font-weight: 600; color: #fff;">{{ request.actor_name }}</td>
              <td style="padding: 12px;">{{ request.leave_date }}</td>
              <td style="padding: 12px;">
                <span
                  :style="{
                    fontSize: '12px',
                    fontWeight: 600,
                    color: getStatusColor(request.status)
                  }"
                >
                  {{ request.status }}
                </span>
              </td>
              <td style="padding: 12px; color: var(--text-secondary);">{{ request.note || '—' }}</td>
              <td style="padding: 12px;">
                <div style="display: flex; gap: 8px;">
                  <button
                    type="button"
                    @click="handleReview(request.id, 'approved')"
                    style="padding: 6px 12px; border-radius: 6px; background: #10b981; color: #fff; border: none; font-size: 13px; font-weight: 600; cursor: pointer;"
                  >
                    批准
                  </button>
                  <button
                    type="button"
                    @click="handleReview(request.id, 'rejected')"
                    style="padding: 6px 12px; border-radius: 6px; background: #ef4444; color: #fff; border: none; font-size: 13px; font-weight: 600; cursor: pointer;"
                  >
                    拒绝
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, LeaveRequest } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";

const authStore = useAuthStore();

const requests = ref<LeaveRequest[]>([]);
const error = ref<string | null>(null);
const success = ref<string | null>(null);

const refreshData = async () => {
  if (!authStore.token) return;
  try {
    requests.value = await adminApi.getLeaveRequests(authStore.token);
  } catch (err: any) {
    console.error("DEBUG RequestsPage:", err);
    error.value = err.message || "获取请假申请失败";
  }
};

onMounted(() => {
  refreshData();
});

const handleReview = async (leaveId: number, status: "approved" | "rejected") => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.reviewLeaveRequest(authStore.token, leaveId, status);
    success.value = `已成功对申请进行 ${status === 'approved' ? '批准' : '拒绝'}。`;
    await refreshData();
  } catch (err: any) {
    error.value = err.message || "审批失败";
  }
};

const getStatusColor = (status: string) => {
  switch (status) {
    case "approved":
      return "#10b981";
    case "rejected":
      return "#ef4444";
    case "pending":
      return "#f59e0b";
    default:
      return "var(--text-secondary)";
  }
};
</script>
