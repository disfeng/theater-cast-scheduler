<template>
  <section aria-label="预指定核对">
    <p v-if="loading" role="status">正在加载预指定</p>
    <p v-else-if="!rows.length">暂无预指定记录</p>
    <article v-for="row in rows" :key="row.id" :id="`predesignation-${row.id}`" :data-testid="`predesignation-${row.id}`"
      :aria-current="row.id === selectedDesignationId ? 'true' : undefined"
      :class="['panel', 'review-card', { 'review-card--selected': row.id === selectedDesignationId }]">
      <header><strong>{{ typeLabel(row.designation_type) }}</strong><span>{{ statusLabel(row.lifecycle_status) }}</span></header>
      <dl>
        <div><dt>使用玩家</dt><dd>{{ row.beneficiary_name }}</dd></div>
        <div><dt>持有人</dt><dd>{{ row.owner_name || "待选择" }}</dd></div>
        <div><dt>目标场次</dt><dd>{{ row.performance_label }}</dd></div>
        <div><dt>演员 / 角色</dt><dd>{{ row.actor_name }} / {{ row.role_name }}</dd></div>
        <div><dt>权益来源 / 到期</dt><dd>{{ row.entitlement_source || "待选券" }} / {{ date(row.entitlement_expiry) }}</dd></div>
        <div><dt>核验人</dt><dd>{{ row.verifier_name || "尚未核验" }}</dd></div>
      </dl>
      <p v-if="row.usage_type === 'proxy' && row.verification_status !== 'verified'" class="pending-reason">等待客服核验持有人授权</p>
      <div v-if="row.usage_type === 'proxy' && row.verification_status !== 'verified'">
        <label>搜索权益持有人<input v-model="forms[row.id].ownerQuery" aria-label="搜索权益持有人" /></label>
        <button @click="searchOwner(row)">搜索持有人</button>
        <button v-for="player in ownerCandidates[row.id] || []" :key="player.id" @click="selectOwner(row, player.id, player.display_name)">选择持有人 {{ player.display_name }}</button>
      </div>
      <p v-if="row.verification_note">核验备注：<span>{{ row.verification_note }}</span></p>
      <p v-if="row.conflict">
        <template v-if="row.comparison === 'higher'">{{ typeLabel(row.designation_type) }}（优先级 {{ row.priority }}）高于 {{ typeLabel(row.conflict.designation_type) }}（优先级 {{ row.conflict.priority }}），需二次确认替换。</template>
        <template v-else-if="row.comparison === 'lower'">{{ typeLabel(row.designation_type) }}优先级较低，保持待处理且不预占权益。</template>
        <template v-else>双方优先级相同，需管理员人工选择，不会自动替换。</template>
      </p>
      <template v-if="canSelect(row)">
        <label>具体权益券
          <select v-model.number="forms[row.id].itemId" aria-label="具体权益券">
            <option :value="0" disabled>请选择</option>
            <option v-for="item in row.available_items" :key="item.id" :value="item.id">{{ item.serial_number }} · {{ item.source_label }} · {{ date(item.expires_at) }}</option>
          </select>
        </label>
        <label v-if="row.usage_type === 'proxy'">核验备注<input v-model="forms[row.id].note" aria-label="核验备注" /></label>
        <button v-if="row.usage_type === 'proxy'" @click="verify(row)">确认代指定并预占</button>
        <button v-else @click="activate(row)">核验并预占</button>
      </template>
      <button v-if="row.action === 'confirm_replace'" @click="replaceTarget = row">替换低优先级指定</button>
      <template v-if="row.action === 'choose_manually'"><button @click="equalTarget=row;equalDecision='choose_incoming'">选择新指定</button><button @click="equalTarget=row;equalDecision='keep_occupied'">保留原指定</button></template>
      <button v-if="row.lifecycle_status === 'predesignated'" @click="cancelTarget = row">取消并退款</button>
      <p v-if="row.lifecycle_status === 'cancelled'">已退款：{{ row.failure_reason }}</p>
      <details><summary>完整状态历史</summary><ol><li v-for="(entry, i) in row.status_history" :key="i">{{ entry.event }} · {{ entry.from_status }} → {{ entry.to_status }} · {{ entry.note || "" }}</li></ol></details>
    </article>
    <div v-if="replaceTarget" role="dialog" aria-label="替换确认" class="panel dialog">
      <p>确认替换并释放原券？</p><button @click="confirmReplace">确认替换</button><button @click="replaceTarget = null">返回</button>
    </div>
    <div v-if="cancelTarget" role="dialog" aria-label="取消指定" class="panel dialog">
      <label>取消原因<input v-model="cancelReason" aria-label="取消原因" /></label><button @click="confirmCancel">确认取消</button><button @click="cancelTarget = null">返回</button>
    </div>
    <div v-if="equalTarget" role="dialog" aria-label="同优先级人工选择" class="panel dialog"><p>确认执行同优先级人工选择？</p><button @click="confirmEqual">二次确认选择</button><button @click="equalTarget=null">返回</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref, watch } from "vue";
import { adminApi, type Predesignation } from "../../api/admin";
import type { PlayerProfile } from "../../features/entitlements/types";
import { useAuthStore } from "../../auth/store";
const auth = useAuthStore(); const rows = ref<Predesignation[]>([]); const loading = ref(true); const error = ref("");
const props = defineProps<{ selectedDesignationId?: number }>();
const selectedDesignationId = ref(props.selectedDesignationId);
watch(() => props.selectedDesignationId, async id => { selectedDesignationId.value = id; await nextTick(); if (id) document.getElementById(`predesignation-${id}`)?.scrollIntoView({ block: "center" }); });
const forms = reactive<Record<number, { itemId: number; note: string; ownerQuery: string; ownerId: number | null }>>({});
const ownerCandidates = reactive<Record<number, PlayerProfile[]>>({});
const replaceTarget = ref<Predesignation | null>(null); const cancelTarget = ref<Predesignation | null>(null); const cancelReason = ref("");
const equalTarget=ref<Predesignation|null>(null);const equalDecision=ref<"choose_incoming"|"keep_occupied">("keep_occupied");
const typeLabel = (v: string) => ({ universal: "万能指定", top_three: "榜单前三指定", paired: "对位指定" }[v] ?? v);
const statusLabel = (v: string | null) => ({ pending_verification: "待客服核验", draft: "待处理", predesignated: "已预指定", cancelled: "已退款", replaced: "已替换", fulfilled: "已核销", unsatisfied: "未满足" }[v || ""] ?? v);
const date = (v: string | null) => v ? new Date(v).toLocaleDateString("zh-CN") : "—";
const setRow = (next: Predesignation) => { const i = rows.value.findIndex(x => x.id === next.id); if (i >= 0) rows.value[i] = next; forms[next.id] ||= { itemId: next.available_items[0]?.id ?? 0, note: next.verification_note ?? "", ownerQuery: "", ownerId: next.owner_player_id }; };
const canSelect = (r: Predesignation) => !["predesignated", "cancelled", "replaced", "fulfilled"].includes(r.lifecycle_status || "") && !r.conflict;
onMounted(async () => { try { rows.value = await adminApi.getDesignations(auth.token!); rows.value.forEach(r => forms[r.id] = { itemId: r.available_items[0]?.id ?? 0, note: r.verification_note ?? "", ownerQuery: "", ownerId: r.owner_player_id }); await nextTick(); if (selectedDesignationId.value) document.getElementById(`predesignation-${selectedDesignationId.value}`)?.scrollIntoView({ block: "center" }); } catch (e: any) { error.value = e.message; } finally { loading.value = false; } });
async function searchOwner(r: Predesignation) { ownerCandidates[r.id] = await adminApi.getPlayerProfiles(auth.token!, forms[r.id].ownerQuery); }
async function selectOwner(r: Predesignation, id: number, name: string) { const [inventory, types] = await Promise.all([adminApi.getPlayerInventory(auth.token!, id), adminApi.getEntitlementItemTypes(auth.token!)]); const type = types.find(t => t.code === r.designation_type); forms[r.id].ownerId=id; r.owner_player_id=id; r.owner_name=name; r.available_items=inventory.items.filter(i => i.item_type_id===type?.id && i.status==="available").sort((a,b)=>a.expires_at.localeCompare(b.expires_at)).map(i=>({ id:i.id,serial_number:i.serial_number,source_label:i.source_label,expires_at:i.expires_at,status:i.status })); forms[r.id].itemId=r.available_items[0]?.id??0; }
async function verify(r: Predesignation) { try { setRow(await adminApi.verifyProxyDesignation(auth.token!, r, { owner_player_id: forms[r.id].ownerId!, item_id: forms[r.id].itemId, note: forms[r.id].note })); } catch (e: any) { error.value = e.message; } }
async function activate(r: Predesignation) { try { setRow(await adminApi.activateDesignation(auth.token!, r, forms[r.id].itemId)); } catch (e: any) { error.value = e.message; } }
async function confirmReplace() { if (!replaceTarget.value) return; try { setRow(await adminApi.replaceDesignation(auth.token!, replaceTarget.value)); replaceTarget.value = null; } catch (e: any) { error.value = e.message; } }
async function confirmCancel() { if (!cancelTarget.value) return; try { setRow(await adminApi.cancelDesignation(auth.token!, cancelTarget.value, cancelReason.value)); cancelTarget.value = null; } catch (e: any) { error.value = e.message; } }
async function confirmEqual(){if(!equalTarget.value)return;try{setRow(await adminApi.resolveEqualDesignation(auth.token!,equalTarget.value,equalDecision.value));equalTarget.value=null}catch(e:any){error.value=e.message}}
</script>

<style scoped>
.review-card{display:grid;gap:12px}.review-card--selected{outline:3px solid var(--primary)}.review-card header{display:flex;justify-content:space-between}.review-card dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.review-card dt{color:var(--text-secondary);font-size:12px}.review-card dd{margin:3px 0}.pending-reason{color:#b45309}.dialog{position:fixed;inset:30% auto auto 50%;transform:translateX(-50%);z-index:10;min-width:320px}
</style>
