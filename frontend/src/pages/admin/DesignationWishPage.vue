<template>
  <section class="page-container">
    <PageHeader title="指定与许愿" description="在此录入每周微信群内的指定场次与许愿信息。支持群统计文本一键解析，自动匹配演员和角色，并校验冲突。" />

    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <!-- Batch Selector Panel -->
    <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 30px; align-items: start; margin-bottom: 30px;">
      <BatchSelector
        v-model="batchForm"
        :theaters="theaters"
        @submit="handleOpenBatch"
      />

      <!-- Active Batch Status Banner & Action -->
      <div v-if="activeBatch" class="panel" style="margin: 0; display: flex; flex-direction: column; gap: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <h3 style="margin-bottom: 6px;">当前批次状态</h3>
            <p style="font-size: 14px; color: var(--text-secondary); margin: 0;">
              剧场：{{ activeTheaterName }} | 对应周一：{{ activeBatch.week_start }}
            </p>
          </div>
          <span
            :style="{
              padding: '6px 12px',
              borderRadius: '20px',
              fontSize: '13px',
              fontWeight: 600,
              background: activeBatch.status === 'ready' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
              color: activeBatch.status === 'ready' ? '#10b981' : '#f59e0b',
              border: activeBatch.status === 'ready' ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid rgba(245, 158, 11, 0.25)'
            }"
          >
            {{ activeBatch.status === "ready" ? "已就绪" : "草稿" }}
          </span>
        </div>

        <div v-if="activeBatch.status === 'ready'" style="padding: 12px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.15); border-radius: 6px; color: #10b981; font-size: 14px; font-weight: 500;">
          批次已就绪，导入内容已锁定。
        </div>

        <div v-else style="display: flex; justify-content: flex-end;">
          <button
            type="button"
            style="padding: 10px 20px; border-radius: 6px; background: #10b981; color: #fff; border: none; font-weight: 600; cursor: pointer;"
            @click="handleMarkReady"
          >
            标记为就绪
          </button>
        </div>
      </div>
    </div>

    <!-- Active Batch Workspaces -->
    <div v-if="activeBatch" style="display: flex; flex-direction: column; gap: 30px;">
      
      <!-- Parse Text Panel -->
      <div v-if="activeBatch.status !== 'ready'" class="panel">
        <h3>导入统计文本</h3>
        <form @submit.prevent="handleParseText" style="display: grid; gap: 16px; margin-top: 10px;">
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label for="raw-text-input">群统计文本</label>
            <textarea
              id="raw-text-input"
              aria-label="群统计文本"
              v-model="rawText"
              placeholder="请粘贴微信群内的指定与许愿统计文本，例如：&#10;#指定信息&#10;【虔诚许愿】-小展/长离-Jennifer"
              required
              style="padding: 12px; border-radius: 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary); min-height: 120px; font-family: monospace; font-size: 14px;"
            />
          </div>
          <div style="display: flex; justify-content: flex-end;">
            <button type="submit" style="padding: 10px 24px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">解析</button>
          </div>
        </form>
      </div>

      <!-- Items Draft Listing Table -->
      <ImportDraftTable
        v-if="draft"
        :draft="draft"
        :actors="actors"
        :roles="roles"
        :performances="performances"
        :isBatchReadOnly="activeBatch.status === 'ready'"
        @addManual="handleAddManualItem"
        @saveItem="handleSaveItem"
        @confirmItem="handleConfirmItem"
      />

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, Theater, Actor, Role, Performance, WeeklyBatch, ImportDraft } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";
import BatchSelector from "../../components/admin/BatchSelector.vue";
import ImportDraftTable from "../../components/admin/ImportDraftTable.vue";

const authStore = useAuthStore();

const theaters = ref<Theater[]>([]);
const actors = ref<Actor[]>([]);
const roles = ref<Role[]>([]);
const performances = ref<Performance[]>([]);

const batchForm = ref({ theaterId: "", weekStart: "" });
const activeBatch = ref<WeeklyBatch | null>(null);

const rawText = ref("");
const draft = ref<ImportDraft | null>(null);

const error = ref<string | null>(null);
const success = ref<string | null>(null);

const activeTheaterName = computed(() => {
  if (!activeBatch.value) return "";
  const t = theaters.value.find((x) => x.id === activeBatch.value?.theater_id);
  return t ? t.name : `剧场 #${activeBatch.value.theater_id}`;
});

const formatLocalDate = (value: Date): string => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

// Fetch initial metadata
onMounted(async () => {
  if (!authStore.token) return;
  try {
    const [tList, aList, rList] = await Promise.all([
      adminApi.getTheaters(authStore.token),
      adminApi.getActors(authStore.token),
      adminApi.getRoles(authStore.token),
    ]);
    theaters.value = tList;
    actors.value = aList;
    roles.value = rList;
  } catch (err: any) {
    error.value = err.message;
  }
});

// Load performances of active batch week range
watch(activeBatch, async (batch) => {
  if (!authStore.token || !batch) {
    performances.value = [];
    return;
  }
  try {
    const dateObj = new Date(batch.week_start);
    const year = dateObj.getFullYear();
    const month = dateObj.getMonth() + 1;
    const weekEnd = new Date(`${batch.week_start}T00:00:00`);
    weekEnd.setDate(weekEnd.getDate() + 6);
    
    const months = [[year, month]];
    if (weekEnd.getFullYear() !== year || weekEnd.getMonth() + 1 !== month) {
      months.push([weekEnd.getFullYear(), weekEnd.getMonth() + 1]);
    }
    
    const groups = await Promise.all(
      months.map(([mYear, mMonth]) =>
        adminApi.getPerformances(authStore.token!, batch.theater_id, mYear, mMonth)
      )
    );
    
    const formattedEnd = formatLocalDate(weekEnd);
    performances.value = groups
      .flat()
      .filter(
        (perf) =>
          perf.performance_date >= batch.week_start &&
          perf.performance_date <= formattedEnd
      );
  } catch (err: any) {
    error.value = err.message;
  }
});

const handleOpenBatch = async () => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    const batch = await adminApi.createWeeklyBatch(authStore.token, {
      theater_id: Number(batchForm.value.theaterId),
      week_start: batchForm.value.weekStart,
    });
    activeBatch.value = batch;

    const drafts = await adminApi.getImportDrafts(authStore.token, batch.id);
    if (drafts.length > 0) {
      draft.value = drafts[0];
    } else {
      draft.value = null;
    }
  } catch (err: any) {
    error.value = err.message || "创建/打开批次失败";
  }
};

const handleMarkReady = async () => {
  if (!authStore.token || !activeBatch.value) return;
  error.value = null;
  success.value = null;
  try {
    const batch = await adminApi.updateWeeklyBatchStatus(authStore.token, activeBatch.value.id, "ready");
    activeBatch.value = batch;
    success.value = "批次已被标记为就绪。";
  } catch (err: any) {
    error.value = err.message || "标记就绪失败";
  }
};

const handleParseText = async () => {
  if (!authStore.token || !activeBatch.value) return;
  error.value = null;
  success.value = null;
  try {
    const parsedDraft = await adminApi.parseImportDraft(authStore.token, activeBatch.value.id, rawText.value);
    draft.value = parsedDraft;
    rawText.value = "";
    success.value = "文本解析成功！";
  } catch (err: any) {
    error.value = err.message || "解析文本失败";
  }
};

const handleAddManualItem = async () => {
  if (!authStore.token || !draft.value) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.createManualItem(authStore.token, draft.value.id, {
      item_kind: "wish",
      designation_type: null,
      player_name: "",
      actor_name_raw: "",
      role_name_raw: "",
      actor_id: null,
      role_id: null,
      target_performance_id: null,
      note: "",
    });
    const updatedDraft = await adminApi.getImportDraft(authStore.token, draft.value.id);
    draft.value = updatedDraft;
  } catch (err: any) {
    error.value = err.message || "添加手动条目失败";
  }
};

const handleSaveItem = async (itemId: number, fields: any) => {
  if (!authStore.token || !draft.value) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.updateDraftItem(authStore.token, itemId, {
      item_kind: fields.item_kind,
      designation_type: fields.designation_type || null,
      player_name: fields.player_name || null,
      actor_name_raw: fields.actor_name_raw || null,
      role_name_raw: fields.role_name_raw || null,
      actor_id: fields.actor_id ? Number(fields.actor_id) : null,
      role_id: fields.role_id ? Number(fields.role_id) : null,
      target_performance_id: fields.target_performance_id ? Number(fields.target_performance_id) : null,
      note: fields.note || null,
    });
    const updatedDraft = await adminApi.getImportDraft(authStore.token, draft.value.id);
    draft.value = updatedDraft;
    success.value = "保存修改成功。";
  } catch (err: any) {
    error.value = err.message || "保存修改失败";
  }
};

const handleConfirmItem = async (itemId: number) => {
  if (!authStore.token || !draft.value) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.confirmDraftItem(authStore.token, itemId);
    const updatedDraft = await adminApi.getImportDraft(authStore.token, draft.value.id);
    draft.value = updatedDraft;
    success.value = "已成功确认并锁定。";
  } catch (err: any) {
    error.value = err.message || "确认失败";
  }
};
</script>
