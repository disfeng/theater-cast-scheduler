<template>
  <section style="max-width: 1200px; margin: 0 auto;">
    <PageHeader title="工作台" description="欢迎回来！这里汇总了你需要复核、审批和导入的待办事项。" />

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <AsyncState :loading="loading" :error="error" @retry="loadData">
      <!-- Grid of Stats Cards -->
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; margin-bottom: 30px;">
        <div class="panel" style="margin: 0; padding: 20px;">
          <div style="color: var(--text-secondary); font-size: 14px; font-weight: 500;">待审批请假</div>
          <div style="font-size: 36px; font-weight: 700; margin: 10px 0; color: #fff;">{{ pendingLeaves.length }}</div>
          <div style="font-size: 12px; color: var(--text-secondary);">需管理员批准 of 请假申请</div>
        </div>

        <div class="panel" style="margin: 0; padding: 20px;">
          <div style="color: var(--text-secondary); font-size: 14px; font-weight: 500;">本月草稿场次</div>
          <div style="font-size: 36px; font-weight: 700; margin: 10px 0; color: #fff;">{{ draftPerformancesCount }}</div>
          <div style="font-size: 12px; color: var(--text-secondary);">尚未正式发布的排班场次</div>
        </div>

        <div class="panel" style="margin: 0; padding: 20px;">
          <div style="color: var(--text-secondary); font-size: 14px; font-weight: 500;">待导入周批次</div>
          <div style="font-size: 36px; font-weight: 700; margin: 10px 0; color: #fff;">{{ draftBatches.length }}</div>
          <div style="font-size: 12px; color: var(--text-secondary);">未锁定或导入中的周排班</div>
        </div>

        <div class="panel" style="margin: 0; padding: 20px;">
          <div style="color: var(--text-secondary); font-size: 14px; font-weight: 500;">活跃演员数</div>
          <div data-metric="actors" style="font-size: 36px; font-weight: 700; margin: 10px 0; color: #fff;">{{ totalActors }}</div>
          <div style="font-size: 12px; color: var(--text-secondary);">当前在册并启用的演员</div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr; gap: 30px;">
        <!-- Pending Leaves List -->
        <div class="panel" style="margin: 0;">
          <h3>待审批请假申请 ({{ pendingLeaves.length }})</h3>
          <p v-if="pendingLeaves.length === 0" style="color: var(--text-secondary); margin-top: 10px;">目前没有等待处理的请假申请。</p>
          <div v-else style="overflow-x: auto; margin-top: 10px;">
            <table style="width: 100%; border-collapse: collapse;">
              <thead>
                <tr style="text-align: left; background: rgba(255, 255, 255, 0.02);">
                  <th style="padding: 12px;">演员</th>
                  <th style="padding: 12px;">请假日期</th>
                  <th style="padding: 12px;">事由/备注</th>
                  <th style="padding: 12px; width: 160px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="leave in pendingLeaves" :key="leave.id" style="border-bottom: 1px solid var(--panel-border);">
                  <td style="padding: 12px; font-weight: 500;">{{ leave.actor_name }}</td>
                  <td style="padding: 12px;">{{ leave.leave_date }}</td>
                  <td style="padding: 12px; color: var(--text-secondary);">{{ leave.note || "无" }}</td>
                  <td style="padding: 12px;">
                    <div style="display: flex; gap: 8px;">
                      <button
                        type="button"
                        @click="handleReviewLeave(leave.id, 'approved', leave.actor_name)"
                        :aria-label="'批准' + leave.actor_name + '的请假'"
                        style="padding: 6px 12px; background: rgba(16, 163, 106, 0.12); border: 1px solid rgba(16, 163, 106, 0.35); color: #087a49; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;"
                      >
                        批准
                      </button>
                      <button
                        type="button"
                        @click="handleReviewLeave(leave.id, 'rejected', leave.actor_name)"
                        :aria-label="'拒绝' + leave.actor_name + '的请假'"
                        style="padding: 6px 12px; background: rgba(220, 63, 69, 0.1); border: 1px solid rgba(220, 63, 69, 0.3); color: #bd2f35; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;"
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

        <!-- Draft Weekly Batches List -->
        <div class="panel" style="margin: 0;">
          <h3>待处理周批次 ({{ draftBatches.length }})</h3>
          <p v-if="draftBatches.length === 0" style="color: var(--text-secondary); margin-top: 10px;">所有周批次均已锁定或完成排班。</p>
          <div v-else style="overflow-x: auto; margin-top: 10px;">
            <table style="width: 100%; border-collapse: collapse;">
              <thead>
                <tr style="text-align: left; background: rgba(255, 255, 255, 0.02);">
                  <th style="padding: 12px;">剧场</th>
                  <th style="padding: 12px;">排班周 (周一)</th>
                  <th style="padding: 12px;">批次状态</th>
                  <th style="padding: 12px;">创建时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="batch in draftBatches" :key="batch.id" style="border-bottom: 1px solid var(--panel-border);">
                  <td style="padding: 12px; font-weight: 500;">
                    {{ theaters.find((t) => t.id === batch.theater_id)?.name || `剧场 ID ${batch.theater_id}` }}
                  </td>
                  <td style="padding: 12px;">{{ batch.week_start }}</td>
                  <td style="padding: 12px;">
                    <span class="badge" :class="batch.status === 'draft' ? 'badge-danger' : 'badge-success'">
                      {{ batch.status === "draft" ? "导入/校正中" : "已确认待排班" }}
                    </span>
                  </td>
                  <td style="padding: 12px; color: var(--text-secondary);">
                    {{ new Date(batch.created_at).toLocaleString() }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, LeaveRequest, WeeklyBatch, Theater } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";
import AsyncState from "../../components/AsyncState.vue";

const authStore = useAuthStore();

const totalActors = ref(0);
const draftPerformancesCount = ref(0);
const pendingLeaves = ref<LeaveRequest[]>([]);
const draftBatches = ref<WeeklyBatch[]>([]);
const theaters = ref<Theater[]>([]);

const loading = ref(true);
const error = ref<string | null>(null);
const success = ref<string | null>(null);

const loadData = async () => {
  if (!authStore.token) return;
  loading.value = true;
  error.value = null;
  try {
    const theatersRes = await adminApi.getTheaters(authStore.token);
    theaters.value = theatersRes;

    const actorsRes = await adminApi.getActors(authStore.token);
    totalActors.value = actorsRes.length;

    const leavesRes = await adminApi.getLeaveRequests(authStore.token);
    pendingLeaves.value = leavesRes.filter((l) => l.status === "pending");

    const batchesRes = await adminApi.getWeeklyBatches(authStore.token);
    draftBatches.value = batchesRes.filter((b) => b.status === "draft" || b.status === "ready");

    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;
    let draftShows = 0;
    
    // Fetch performances concurrently
    await Promise.all(
      theatersRes.map(async (t) => {
        try {
          const perfs = await adminApi.getPerformances(authStore.token!, t.id, currentYear, currentMonth);
          draftShows += perfs.filter((p) => p.status === "draft").length;
        } catch {}
      })
    );
    draftPerformancesCount.value = draftShows;
  } catch (err: any) {
    error.value = err.message || "加载仪表盘数据失败";
  } finally {
    loading.value = false;
  }
};

const handleReviewLeave = async (leaveId: number, status: "approved" | "rejected", actorName: string) => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.reviewLeaveRequest(authStore.token, leaveId, status);
    success.value = status === "approved" ? `已批准${actorName}的请假` : `已拒绝${actorName}的请假`;
    await loadData();
  } catch (err: any) {
    error.value = err.message || "审批失败";
  }
};

onMounted(() => {
  loadData();
});
</script>
