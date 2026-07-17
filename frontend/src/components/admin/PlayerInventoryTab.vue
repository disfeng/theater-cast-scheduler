<template>
  <div class="workspace">
    <el-card shadow="never"
      ><template #header><strong>玩家权益背包</strong></template>
      <div class="search">
        <input
          v-model="query"
          aria-label="搜索玩家权益"
          placeholder="输入玩家名或别名"
          :disabled="busy"
          @keyup.enter="search"
        /><el-button
          type="primary"
          :loading="pending === 'search'"
          :disabled="busy"
          @click="search"
          >搜索</el-button
        >
      </div>
      <div v-if="pending === 'search'" role="status">正在搜索玩家…</div>
      <el-empty
        v-else-if="searchDone && !players.length"
        description="未找到匹配玩家"
      />
      <div v-else class="players">
        <div v-for="player in players" :key="player.id" class="player">
          <span
            ><strong>{{ player.display_name }}</strong
            ><el-tag
              size="small"
              :type="player.status === 'active' ? 'success' : 'warning'"
              >{{ player.status === "active" ? "正式" : "待确认" }}</el-tag
            ></span
          ><el-button
            size="small"
            :loading="pending === 'inventory' && loadingPlayer === player.id"
            :disabled="busy"
            :aria-label="`查看 ${player.display_name} 的权益`"
            @click="loadInventory(player.id)"
            >查看背包</el-button
          >
        </div>
      </div>
    </el-card>
    <div v-if="pending === 'inventory'" role="status">正在加载权益背包…</div>
    <template v-else-if="inventory"
      ><div class="heading">
        <div>
          <h3>{{ inventory.player.display_name }}的权益背包</h3>
          <p>每张权益独立展示来源、有效期与完整流水。</p>
        </div>
        <el-tag>{{ inventory.items.length }} 张</el-tag>
      </div>
      <el-empty v-if="!inventory.items.length" description="该玩家暂无权益" />
      <div class="grid">
        <el-card
          v-for="item in inventory.items"
          :key="item.id"
          data-testid="inventory-item-card"
          shadow="hover"
          ><template #header
            ><div class="heading">
              <strong>{{ item.serial_number }}</strong
              ><el-tag size="small" :type="statusType(item.status)">{{
                entitlementLabel(item.status)
              }}</el-tag>
            </div></template
          >
          <dl>
            <dt>权益类型</dt>
            <dd>{{ typeName(item.item_type_id) }}</dd>
            <dt>来源</dt>
            <dd>{{ item.source_label }}</dd>
            <dt>到期</dt>
            <dd>{{ formatEntitlementDate(item.expires_at) }}</dd>
          </dl>
          <el-timeline
            ><el-timeline-item
              v-for="entry in item.ledger_entries"
              :key="entry.id"
              :timestamp="formatEntitlementDate(entry.occurred_at)"
              placement="top"
              ><strong>{{ entitlementLabel(entry.event_type) }}</strong
              ><span v-if="entry.reason">
                · {{ entry.reason }}</span
              ></el-timeline-item
            ></el-timeline
          >
          <div class="actions">
            <el-button
              size="small"
                :disabled="busy || item.status === 'revoked'"
              @click="openAction('extend', item)"
              >延期</el-button
            ><el-button
                v-if="item.status !== 'revoked'"
              size="small"
              type="danger"
              plain
              :disabled="busy"
              @click="openAction('void', item)"
              >作废</el-button
            ><el-button
              v-else
              size="small"
              type="success"
              plain
              :disabled="busy"
              @click="openAction('restore', item)"
              >恢复</el-button
            >
          </div></el-card
        >
      </div></template
    >
    <el-dialog
      v-model="dialogOpen"
      :title="dialogTitle"
      width="min(480px, 92vw)"
      :close-on-click-modal="false"
      ><template v-if="selectedItem"
        ><el-descriptions :column="1" border
          ><el-descriptions-item label="权益序列号">{{
            selectedItem.serial_number
          }}</el-descriptions-item
          ><el-descriptions-item label="当前状态">{{
            entitlementLabel(selectedItem.status)
          }}</el-descriptions-item
          ><el-descriptions-item v-if="action === 'extend'" label="原到期日">{{
            formatEntitlementDate(selectedItem.expires_at)
          }}</el-descriptions-item></el-descriptions
        ><el-alert
          v-if="action === 'void'"
          title="作废后该权益将不可用于指定；如需恢复必须再次明确操作。"
          type="warning"
          show-icon
          :closable="false" /><el-alert
          v-if="action === 'restore'"
          title="恢复后权益将按当前到期日重新计算可用状态。"
          type="info"
          show-icon
          :closable="false" /><label v-if="action === 'extend'" class="field"
          >新到期日<input
            v-model="actionForm.date"
            aria-label="新到期日"
            type="date" /></label
        ><label class="field"
          >操作原因<textarea
            v-model="actionForm.reason"
            aria-label="操作原因"
            rows="3"
          /></label></template
      ><template #footer
        ><el-button
          :disabled="pending === 'mutation'"
          @click="dialogOpen = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="pending === 'mutation'"
          :disabled="!validAction"
          @click="submitAction"
          >{{ confirmLabel }}</el-button
        ></template
      ></el-dialog
    >
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type {
  EntitlementItem,
  EntitlementItemType,
  PlayerInventory,
  PlayerProfile,
} from "../../features/entitlements/types";
import {
  entitlementLabel,
  formatEntitlementDate,
  toIsoEndOfDay,
} from "../../features/entitlements/format";
const auth = useAuthStore(),
  query = ref(""),
  players = ref<PlayerProfile[]>([]),
  inventory = ref<PlayerInventory | null>(null),
  itemTypes = ref<EntitlementItemType[]>([]),
  error = ref(""),
  pending = ref<"" | "search" | "inventory" | "mutation">(""),
  searchDone = ref(false),
  loadingPlayer = ref<number | null>(null),
  dialogOpen = ref(false),
  selectedItem = ref<EntitlementItem | null>(null),
  action = ref<"extend" | "void" | "restore">("void"),
  actionForm = reactive({ date: "", reason: "" });
const busy = computed(() => !!pending.value),
  dialogTitle = computed(
    () =>
      ({ extend: "延期权益", void: "作废权益", restore: "恢复权益" })[
        action.value
      ],
  ),
  confirmLabel = computed(
    () =>
      ({ extend: "确认延期", void: "确认作废", restore: "确认恢复" })[
        action.value
      ],
  ),
  validAction = computed(
    () =>
      !!actionForm.reason.trim() &&
      (action.value !== "extend" || !!actionForm.date),
  );
onMounted(async () => {
  if (auth.token)
    try {
      itemTypes.value = await adminApi.getEntitlementItemTypes(auth.token);
    } catch (e: any) {
      error.value = e.message;
    }
});
const typeName = (id: number) =>
    itemTypes.value.find((t) => t.id === id)?.display_name ?? `类型 #${id}`,
  statusType = (s: string) =>
  s === "available" ? "success" : s === "revoked" ? "danger" : "warning";
async function search() {
  if (!auth.token || busy.value) return;
  pending.value = "search";
  searchDone.value = false;
  inventory.value = null;
  players.value = [];
  error.value = "";
  try {
    players.value = await adminApi.getPlayerProfiles(
      auth.token,
      query.value.trim(),
    );
  } catch (e: any) {
    error.value = e.message;
  } finally {
    pending.value = "";
    searchDone.value = true;
  }
}
async function loadInventory(id: number) {
  if (!auth.token || busy.value) return;
  pending.value = "inventory";
  loadingPlayer.value = id;
  inventory.value = null;
  error.value = "";
  try {
    inventory.value = await adminApi.getPlayerInventory(auth.token, id);
  } catch (e: any) {
    error.value = e.message;
  } finally {
    pending.value = "";
    loadingPlayer.value = null;
  }
}
function openAction(next: typeof action.value, item: EntitlementItem) {
  action.value = next;
  selectedItem.value = item;
  actionForm.date = "";
  actionForm.reason = "";
  dialogOpen.value = true;
}
function replace(item: EntitlementItem) {
  if (inventory.value)
    inventory.value.items = inventory.value.items.map((old) =>
      old.id === item.id ? item : old,
    );
}
async function submitAction() {
  if (!auth.token || !selectedItem.value || !validAction.value || busy.value)
    return;
  pending.value = "mutation";
  error.value = "";
  try {
    let next;
    if (action.value === "extend")
      next = await adminApi.extendEntitlementItem(
        auth.token,
        selectedItem.value.id,
        {
          expires_at: toIsoEndOfDay(actionForm.date)!,
          reason: actionForm.reason.trim(),
        },
      );
    else if (action.value === "void")
      next = await adminApi.voidEntitlementItem(
        auth.token,
        selectedItem.value.id,
        { reason: actionForm.reason.trim() },
      );
    else
      next = await adminApi.restoreEntitlementItem(
        auth.token,
        selectedItem.value.id,
        { reason: actionForm.reason.trim() },
      );
    replace(next);
    dialogOpen.value = false;
    ElMessage.success("权益状态已更新");
  } catch (e: any) {
    error.value = e.message;
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
.search {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}
.search input,
.field input,
.field textarea {
  padding: 8px 10px;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text-primary);
}
.players {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.player,
.heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.player {
  padding: 8px 10px;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
}
.player span {
  display: flex;
  gap: 8px;
}
.heading h3,
.heading p {
  margin: 0;
}
.heading p {
  font-size: 13px;
  color: var(--text-secondary);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
dl {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 7px;
  font-size: 13px;
}
dt {
  color: var(--text-secondary);
}
dd {
  margin: 0;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}
.field {
  display: grid;
  gap: 6px;
  margin-top: 14px;
}
@media (max-width: 1000px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
