<template>
  <section style="max-width: 1200px; margin: 0 auto;">
    <PageHeader title="演员管理" description="在此新增并管理在册演员的基础排班偏好、评级以及角色出演能力。" />

    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 30px; align-items: start;">
      
      <!-- Left Column: Add Actor Form -->
      <div class="panel" style="margin: 0;">
        <h3>新增演员</h3>
        <form @submit.prevent="handleCreateActor" style="display: grid; gap: 16px; margin-top: 10px;">
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="actor-name-input">演员姓名</label>
            <input
              id="actor-name-input"
              aria-label="演员姓名"
              v-model="displayName"
              placeholder="例如：小展"
              required
              style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
            />
          </div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="actor-rating-select">演员评级</label>
            <select
              id="actor-rating-select"
              aria-label="演员评级"
              v-model="ratingLevel"
              style="padding: 8px 12px; border-radius: 6px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
            >
              <option value="high">高</option>
              <option value="normal">普通</option>
              <option value="low">低</option>
              <option value="suspended">暂停</option>
            </select>
          </div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="actor-consecutive-input">最大连场</label>
            <input
              id="actor-consecutive-input"
              aria-label="最大连场"
              type="number"
              min="1"
              max="3"
              v-model.number="maxConsecutive"
              required
              style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
            />
          </div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="actor-monthly-cap-input">低评级上限</label>
            <input
              id="actor-monthly-cap-input"
              type="number"
              min="0"
              v-model.number="monthlyCap"
              style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
            />
          </div>

          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="actor-notes-input">备注</label>
            <input
              id="actor-notes-input"
              v-model="notes"
              style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
            />
          </div>

          <button type="submit" style="margin-top: 8px; padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">保存演员</button>
        </form>
      </div>

      <!-- Right Column: Actors List -->
      <div class="panel" style="margin: 0;">
        <h3>演员列表 ({{ actors.length }})</h3>
        <p v-if="actors.length === 0" style="color: var(--text-secondary); margin-top: 10px;">暂无演员记录。</p>
        <div v-else style="display: grid; gap: 20px; margin-top: 16px;">
          <ActorEditor
            v-for="actor in actors"
            :key="actor.id"
            :actor="actor"
            :roles="roles"
            :token="authStore.token || ''"
            @refresh="refreshData"
            @error="setError"
          />
        </div>
      </div>

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, Actor, Role } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";
import ActorEditor from "../../components/admin/ActorEditor.vue";

const authStore = useAuthStore();

const actors = ref<Actor[]>([]);
const roles = ref<Role[]>([]);

const displayName = ref("");
const ratingLevel = ref<"high" | "normal" | "low" | "suspended">("normal");
const maxConsecutive = ref(3);
const monthlyCap = ref<number | null>(null);
const notes = ref("");
const error = ref<string | null>(null);

const setError = (msg: string | null) => {
  error.value = msg;
};

const refreshData = () => {
  if (!authStore.token) return;
  adminApi.getActors(authStore.token).then((res) => actors.value = res).catch((err) => error.value = err.message);
  adminApi.getRoles(authStore.token).then((res) => roles.value = res).catch((err) => error.value = err.message);
};

onMounted(() => {
  refreshData();
});

const handleCreateActor = async () => {
  if (!authStore.token) return;
  error.value = null;
  try {
    await adminApi.createActor(authStore.token, {
      display_name: displayName.value,
      rating_level: ratingLevel.value,
      max_consecutive_performances: maxConsecutive.value,
      low_rating_monthly_cap: monthlyCap.value || null,
      notes: notes.value || null,
    });
    displayName.value = "";
    ratingLevel.value = "normal";
    maxConsecutive.value = 3;
    monthlyCap.value = null;
    notes.value = "";
    refreshData();
  } catch (err: any) {
    error.value = err.message || "创建演员失败";
  }
};
</script>
