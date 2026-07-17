<template>
  <section class="designation-review">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-empty v-if="!rows.length" description="暂无指定" :image-size="72" />
    <article v-for="row in rows" :key="row.id" class="designation-card">
      <header>
        <div><strong>{{ row.beneficiary_name }}</strong><p>{{ typeLabel(row.designation_type) }} · {{ row.actor_name }} / {{ row.role_name }}</p></div>
        <el-tag :type="statusType(row.lifecycle_status)">{{ statusLabel(row.lifecycle_status) }}</el-tag>
      </header>
      <dl>
        <div><dt>权益持有人</dt><dd>{{ row.owner_name || "待核验" }}</dd></div>
        <div><dt>使用方式</dt><dd>{{ row.usage_type === "proxy" ? "代指定" : "本人指定" }}</dd></div>
        <div><dt>权益来源</dt><dd>{{ row.entitlement_source || "待选择" }}</dd></div>
        <div><dt>到期日</dt><dd>{{ formatDate(row.entitlement_expiry) }}</dd></div>
      </dl>

      <el-alert v-if="row.conflict" :title="conflictText(row)" :type="row.comparison === 'lower' ? 'warning' : 'error'" :closable="false" />
      <div v-if="row.usage_type === 'proxy' && row.verification_status !== 'verified'" class="proxy-check">
        <el-input v-model="form(row).ownerQuery" aria-label="搜索权益持有人" placeholder="输入持有人昵称" />
        <el-button @click="searchOwner(row)">搜索</el-button>
        <el-button v-for="candidate in ownerCandidates[row.id] || []" :key="candidate.id" @click="selectOwner(row, candidate)">选择 {{ candidate.display_name }}</el-button>
        <el-input v-model="form(row).note" aria-label="核验备注" placeholder="记录客服核验依据" />
      </div>

      <div v-if="canChooseItem(row)" class="item-choice">
        <el-select v-model="form(row).itemId" aria-label="具体权益券" placeholder="选择具体权益">
          <el-option v-for="item in row.available_items" :key="item.id" :label="`${item.serial_number} · ${item.source_label}`" :value="item.id" />
        </el-select>
        <span v-if="selectedItem(row)">到期 {{ formatDate(selectedItem(row)?.expires_at || null) }}</span>
      </div>

      <div class="actions">
        <el-button v-if="row.usage_type === 'proxy' && row.verification_status !== 'verified' && !row.conflict" type="primary" :disabled="!form(row).ownerId || !form(row).itemId || busyId === row.id" @click="verify(row)">确认代指定并预占</el-button>
        <el-button v-else-if="row.action === 'activate' || (!row.conflict && !terminal(row))" type="primary" :disabled="!form(row).itemId || busyId === row.id" @click="activate(row)">核验并预占</el-button>
        <el-button v-if="row.action === 'confirm_replace'" type="warning" :disabled="busyId === row.id" @click="replace(row)">替换低优先级指定</el-button>
        <template v-if="row.action === 'choose_manually'">
          <el-button type="primary" plain :disabled="busyId === row.id" @click="resolveEqual(row, 'choose_incoming')">选择新指定</el-button>
          <el-button :disabled="busyId === row.id" @click="resolveEqual(row, 'keep_occupied')">保留原指定</el-button>
        </template>
        <el-button v-if="!terminal(row)" type="danger" plain :aria-label="`拒绝指定 ${row.beneficiary_name}`" @click="$emit('reject', row.id)">拒绝</el-button>
      </div>
      <p v-if="row.failure_reason" class="failure">处理原因：{{ row.failure_reason }}</p>
      <details v-if="row.status_history?.length"><summary>状态历史</summary><ol><li v-for="(entry, index) in row.status_history" :key="index">{{ entry.event }} · {{ entry.from_status || "无" }} → {{ entry.to_status || "无" }}<span v-if="entry.note"> · {{ entry.note }}</span></li></ol></details>
    </article>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { adminApi, type Predesignation } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { PlayerProfile } from "../../features/entitlements/types";

const props = defineProps<{ rows: Predesignation[] }>();
const emit = defineEmits<{ changed: []; reject: [id: number] }>();
const auth = useAuthStore();
const forms = reactive<Record<number, { itemId: number; note: string; ownerQuery: string; ownerId: number | null }>>({});
const ownerCandidates = reactive<Record<number, PlayerProfile[]>>({});
const busyId = ref<number | null>(null);
const error = ref("");
function form(row: Predesignation) { return forms[row.id] ||= { itemId: row.entitlement_item_id || row.available_items?.[0]?.id || 0, note: row.verification_note || "", ownerQuery: "", ownerId: row.owner_player_id }; }
function selectedItem(row: Predesignation) { return row.available_items?.find(item => item.id === form(row).itemId); }
function terminal(row: Predesignation) { return ["cancelled", "replaced", "fulfilled", "unsatisfied"].includes(row.lifecycle_status || ""); }
function canChooseItem(row: Predesignation) { return !terminal(row) && !row.entitlement_item_id && !!row.available_items?.length; }
async function run(row: Predesignation, action: () => Promise<unknown>) { busyId.value = row.id; error.value = ""; try { await action(); emit("changed"); } catch (cause: any) { error.value = cause.message || "指定操作失败"; } finally { busyId.value = null; } }
async function activate(row: Predesignation) { await run(row, () => adminApi.activateDesignation(auth.token!, row, form(row).itemId)); }
async function verify(row: Predesignation) { await run(row, () => adminApi.verifyProxyDesignation(auth.token!, row, { owner_player_id: form(row).ownerId!, item_id: form(row).itemId, note: form(row).note })); }
async function replace(row: Predesignation) { await ElMessageBox.confirm("替换后将释放原指定预占的权益，是否继续？", "二次确认", { type: "warning", confirmButtonText: "确认替换", cancelButtonText: "取消" }); await run(row, () => adminApi.replaceDesignation(auth.token!, row)); }
async function resolveEqual(row: Predesignation, decision: "choose_incoming" | "keep_occupied") { await ElMessageBox.confirm(decision === "choose_incoming" ? "确认选择新指定并释放原指定权益？" : "确认保留原指定，新指定继续保持未生效？", "同优先级人工决策", { type: "warning", confirmButtonText: decision === "choose_incoming" ? "确认选择新指定" : "确认保留原指定", cancelButtonText: "取消" }); await run(row, () => adminApi.resolveEqualDesignation(auth.token!, row, decision)); }
async function searchOwner(row: Predesignation) { ownerCandidates[row.id] = await adminApi.getPlayerProfiles(auth.token!, form(row).ownerQuery); }
async function selectOwner(row: Predesignation, player: PlayerProfile) { const [inventory, types] = await Promise.all([adminApi.getPlayerInventory(auth.token!, player.id), adminApi.getEntitlementItemTypes(auth.token!)]); const type = types.find(item => item.code === row.designation_type); row.owner_player_id = player.id; row.owner_name = player.display_name; row.available_items = inventory.items.filter(item => item.item_type_id === type?.id && item.status === "available").map(item => ({ id: item.id, serial_number: item.serial_number, source_label: item.source_label, expires_at: item.expires_at, status: item.status })); Object.assign(form(row), { ownerId: player.id, itemId: row.available_items[0]?.id || 0 }); }
const typeLabel = (value: string) => ({ universal: "万能指定", top_three: "榜单前三指定", paired: "对位指定" }[value] || value);
const statusLabel = (value: string | null) => ({ draft: "待核对", pending_verification: "待客服核验", predesignated: "已预指定", cancelled: "已拒绝/退款", replaced: "已替换", fulfilled: "已核销", unsatisfied: "未满足" }[value || ""] || value || "待处理");
const statusType = (value: string | null): "success" | "warning" | "danger" | "info" => value === "predesignated" || value === "fulfilled" ? "success" : value === "cancelled" || value === "unsatisfied" ? "danger" : "warning";
const formatDate = (value: string | null) => value ? new Date(value).toLocaleDateString("zh-CN") : "—";
const conflictText = (row: Predesignation) => row.comparison === "higher" ? "新指定优先级更高，需二次确认替换" : row.comparison === "equal" ? "同优先级冲突，需人工决策" : "当前指定优先级较低，不会自动预占";
</script>

<style scoped>
.designation-review{display:grid;gap:12px}.designation-card{display:grid;gap:13px;padding:15px;border:1px solid #e2e7ef;border-radius:11px}.designation-card header,.actions,.item-choice,.proxy-check{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.designation-card header{justify-content:space-between}.designation-card p{margin:4px 0 0;color:#68758d}.designation-card dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0}.designation-card dt{color:#8490a4;font-size:12px}.designation-card dd{margin:3px 0 0}.item-choice .el-select{width:280px}.item-choice span{color:#8490a4;font-size:12px}.proxy-check .el-input{max-width:260px}.failure{color:#d84f4f!important}details{color:#64748b}details li{margin:5px 0}@media(max-width:640px){.designation-card dl{grid-template-columns:1fr}.item-choice .el-select{width:100%}}
</style>
