<template>
  <div class="workspace">
    <el-card shadow="never"
      ><template #header
        ><div class="heading">
          <strong>月度发放批次</strong
          ><el-tag v-if="batch" :type="readOnly ? 'success' : 'warning'">{{
            readOnly ? "已确认，只读" : "草稿"
          }}</el-tag>
        </div></template
      >
      <div class="form-grid">
        <label
          >来源月份<input
            v-model="sourceMonth"
            aria-label="来源月份"
            type="month"
            :disabled="readOnly || busy" /></label
        ><label
          >批次名称<input
            v-model="title"
            aria-label="批次名称"
            :disabled="readOnly || busy" /></label
        ><el-button
          type="primary"
          :loading="pending === 'create'"
          :disabled="busy || !sourceMonth || !!batch"
          @click="createDraft"
          >创建草稿</el-button
        >
      </div>
    </el-card>
    <el-skeleton
      v-if="initialLoading"
      :rows="2"
      animated
      aria-label="正在加载发放批次"
    />
    <el-card v-else-if="batches.length" shadow="never"
      ><template #header><strong>已有批次</strong></template>
      <div class="button-list">
        <el-button
          v-for="saved in batches"
          :key="saved.id"
          size="small"
          :type="batch?.id === saved.id ? 'primary' : 'default'"
          :aria-label="`打开批次 ${saved.title || saved.source_label}`"
          :disabled="busy"
          @click="openBatch(saved)"
          >{{ saved.title || saved.source_label }} ·
          {{ saved.status === "granted" ? "已确认" : saved.status === "cancelled" ? "已取消" : "草稿" }}</el-button
        >
      </div></el-card
    >
    <el-empty v-else-if="!batch" description="暂无发放批次，可创建首个草稿" />
    <template v-if="batch">
      <el-card shadow="never"
        ><template #header><strong>添加玩家权益</strong></template>
        <div class="form-grid">
          <label
            >玩家搜索<input
              v-model="playerQuery"
              aria-label="玩家搜索"
              :disabled="readOnly"
              @input="schedulePlayerSearch" /></label
          ><label
            >权益类型<select
              v-model.number="itemTypeId"
              aria-label="权益类型"
              :disabled="readOnly || busy"
            >
              <option v-for="type in itemTypes" :key="type.id" :value="type.id">
                {{ type.display_name }}
              </option>
            </select></label
          ><label
            >权益数量<input
              v-model.number="quantity"
              aria-label="权益数量"
              type="number"
              min="1"
              max="20"
              step="1"
              :disabled="readOnly || busy" /></label
          ><el-button
            :disabled="readOnly || busy || !selectedPlayer"
            @click="addItems"
            >添加权益</el-button
          >
        </div>
        <div v-if="pending === 'search'" role="status">正在搜索玩家…</div>
        <div v-else-if="searchDone && !players.length" class="hint">
          未找到匹配玩家
        </div>
        <div class="button-list">
          <el-button
            v-for="player in players"
            :key="player.id"
            size="small"
            plain
            :disabled="player.status !== 'active' || busy"
            :aria-label="`选择玩家 ${player.display_name}`"
            @click="selectedPlayer = player"
            >{{ player.display_name }} ·
            {{
              player.status === "active" ? "正式" : "不可发放（仅限正式玩家）"
            }}</el-button
          >
        </div>
        <p v-if="selectedPlayer" class="hint">
          当前玩家：<strong>{{ selectedPlayer.display_name }}</strong>
        </p>
      </el-card>
      <div class="item-grid">
        <el-card
          v-for="(item, index) in items"
          :key="item.id ?? index"
          data-testid="grant-item-card"
          shadow="hover"
          ><template #header
            ><div class="heading">
              <strong>权益 #{{ index + 1 }}</strong
              ><el-tag size="small">{{ typeName(item.item_type_id) }}</el-tag>
            </div></template
          >
          <div class="item-fields">
            <label
              >权益来源<input
                v-model="item.source_label"
                aria-label="权益来源"
                :disabled="readOnly || busy" /></label
            ><label
              >到期日期<input
                v-model="item.expires_at"
                aria-label="到期日期"
                type="date"
                :disabled="readOnly || busy" /></label
            ><label
              >备注<input
                v-model="item.notes"
                aria-label="权益备注"
                :disabled="readOnly || busy"
            /></label></div
        ></el-card>
      </div>
      <div class="actions">
        <el-button
          :loading="pending === 'save'"
          :disabled="readOnly || busy || !items.length"
          @click="saveDraft"
          >保存草稿</el-button
        ><el-button
          type="primary"
          :loading="pending === 'confirm'"
          :disabled="readOnly || busy || !items.length"
          @click="confirmBatch"
          >确认发放</el-button
        >
      </div>
    </template>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    />
  </div>
</template>
<script setup lang="ts">
import { onBeforeUnmount } from "vue";
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type {
  EntitlementItemType,
  GrantBatch,
  GrantDraftItem,
  PlayerProfile,
} from "../../features/entitlements/types";
import {
  businessDateInput,
  monthStart,
  toIsoEndOfDay,
} from "../../features/entitlements/format";
const auth = useAuthStore(),
  sourceMonth = ref(""),
  title = ref(""),
  batch = ref<GrantBatch | null>(null),
  batches = ref<GrantBatch[]>([]),
  itemTypes = ref<EntitlementItemType[]>([]),
  itemTypeId = ref<number | null>(null),
  playerQuery = ref(""),
  players = ref<PlayerProfile[]>([]),
  selectedPlayer = ref<PlayerProfile | null>(null),
  quantity = ref(1),
  items = ref<(GrantDraftItem & { expires_at: string })[]>([]),
  error = ref(""),
  pending = ref<"" | "create" | "save" | "confirm" | "search">(""),
  initialLoading = ref(true),
  searchDone = ref(false);
const readOnly = computed(() => batch.value?.status !== "draft"),
  busy = computed(() => !!pending.value);
onMounted(async () => {
  if (!auth.token) return;
  try {
    const [types, saved] = await Promise.all([
      adminApi.getEntitlementItemTypes(auth.token),
      adminApi.getGrantBatches(auth.token),
    ]);
    itemTypes.value = types;
    itemTypeId.value = types[0]?.id ?? null;
    batches.value = saved;
  } catch (e: any) {
    error.value = e.message;
  } finally {
    initialLoading.value = false;
  }
});
const typeName = (id: number) =>
    itemTypes.value.find((t) => t.id === id)?.display_name ?? `类型 #${id}`,
  defaultLabel = () =>
    `${sourceMonth.value.slice(0, 4)} 年 ${Number(sourceMonth.value.slice(5))} 月月度发放`;
const payload = () => ({
  source_month: monthStart(sourceMonth.value),
  source_label: defaultLabel(),
  title:
    title.value ||
    `${sourceMonth.value.slice(0, 4)} 年 ${Number(sourceMonth.value.slice(5))} 月权益`,
  grant_date: null,
  default_expires_at: null,
  notes: null,
  items: items.value.map((item) => ({
    ...item,
    quantity: 1,
    source_month: monthStart(sourceMonth.value),
    expires_at: toIsoEndOfDay(item.expires_at),
  })),
});
function openBatch(saved: GrantBatch) {
  batch.value = saved;
  sourceMonth.value = saved.source_month.slice(0, 7);
  title.value = saved.title ?? "";
  items.value = saved.draft_items.map((item) => ({
    ...item,
    quantity: 1,
    expires_at: businessDateInput(item.expires_at),
  }));
  selectedPlayer.value = null;
  players.value = [];
}
function replaceBatch(saved: GrantBatch) {
  batch.value = saved;
  batches.value = [saved, ...batches.value.filter((x) => x.id !== saved.id)];
}
async function createDraft() {
  if (!auth.token || busy.value) return;
  pending.value = "create";
  error.value = "";
  try {
    replaceBatch(await adminApi.createGrantBatch(auth.token, payload()));
  } catch (e: any) {
    error.value = e.message;
  } finally {
    pending.value = "";
  }
}
let searchTimer: ReturnType<typeof setTimeout> | null = null,
  searchSequence = 0,
  searchController: AbortController | null = null;
function schedulePlayerSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  searchController?.abort();
  const query = playerQuery.value.trim();
  const sequence = ++searchSequence;
  selectedPlayer.value = null;
  if (!query) {
    players.value = [];
    searchDone.value = false;
    pending.value = "";
    return;
  }
  searchTimer = setTimeout(() => runPlayerSearch(query, sequence), 250);
}
async function runPlayerSearch(query: string, sequence: number) {
  if (!auth.token) return;
  searchController = new AbortController();
  pending.value = "search";
  searchDone.value = false;
  try {
    const result = await adminApi.getPlayerProfiles(
      auth.token,
      query,
      searchController.signal,
    );
    if (sequence === searchSequence) players.value = result;
  } catch (e: any) {
    if (e?.name !== "AbortError" && sequence === searchSequence)
      error.value = e.message;
  } finally {
    if (sequence === searchSequence) {
      pending.value = "";
      searchDone.value = true;
    }
  }
}
onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
  searchController?.abort();
  searchSequence++;
});
function addItems() {
  if (
    !selectedPlayer.value ||
    selectedPlayer.value.status !== "active" ||
    !itemTypeId.value
  )
    return;
  if (
    !Number.isInteger(quantity.value) ||
    quantity.value < 1 ||
    quantity.value > 20
  ) {
    error.value = "权益数量必须是 1 到 20 的整数";
    return;
  }
  error.value = "";
  for (let i = 0; i < quantity.value; i++)
    items.value.push({
      player_id: selectedPlayer.value.id,
      item_type_id: itemTypeId.value,
      quantity: 1,
      source_month: monthStart(sourceMonth.value),
      source_label: defaultLabel(),
      expires_at: "",
      notes: null,
    });
}
async function persist(mode: "save" | "confirm") {
  if (!auth.token || !batch.value) return false;
  pending.value = mode;
  error.value = "";
  try {
    replaceBatch(
      await adminApi.updateGrantBatch(auth.token, batch.value.id, payload()),
    );
    return true;
  } catch (e: any) {
    error.value = e.message;
    return false;
  } finally {
    if (mode === "save") pending.value = "";
  }
}
async function saveDraft() {
  if (!busy.value && (await persist("save"))) ElMessage.success("草稿已保存");
}
async function confirmBatch() {
  if (!auth.token || !batch.value || busy.value) return;
  try {
    await ElMessageBox.confirm(
      `批次“${title.value || defaultLabel()}”将发放 ${items.value.length} 张独立权益。确认后不可修改。`,
      "确认月度发放",
      { confirmButtonText: "确认", cancelButtonText: "取消", type: "warning" },
    );
    if (!(await persist("confirm"))) return;
    replaceBatch(await adminApi.confirmGrantBatch(auth.token, batch.value.id));
    ElMessage.success("发放已确认");
  } catch (e: any) {
    if (e !== "cancel" && e !== "close") error.value = e.message;
  } finally {
    pending.value = "";
  }
}
</script>
<style scoped>
.workspace {
  display: grid;
  gap: 14px;
}
.heading,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.form-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1.4fr) minmax(160px, 1fr) minmax(
      110px,
      0.6fr
    ) auto;
  gap: 12px;
  align-items: end;
}
.form-grid label,
.item-fields label {
  display: grid;
  gap: 5px;
  font-size: 13px;
  color: var(--text-secondary);
}
input,
select {
  min-height: 36px;
  padding: 7px 10px;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text-primary);
}
.button-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.hint {
  font-size: 13px;
  color: var(--text-secondary);
}
.item-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.item-fields {
  display: grid;
  gap: 10px;
}
.actions {
  justify-content: flex-end;
}
@media (max-width: 900px) {
  .form-grid,
  .item-grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 600px) {
  .form-grid,
  .item-grid {
    grid-template-columns: 1fr;
  }
  .actions {
    flex-wrap: wrap;
  }
}
</style>
