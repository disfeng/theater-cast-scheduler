<template>
  <div class="grant-workspace">
    <div v-if="!activeDefinitions.length" class="empty-panel"><el-empty description="请先在道具配置中启用至少一种道具" /></div>
    <template v-else>
      <section class="batch-panel">
        <div class="section-heading"><div><h2>权益发放</h2><p>设定批次默认值，再按玩家填写各类道具数量。</p></div><el-tag v-if="batch" :type="batch.status==='draft'?'warning':'success'">{{ batch.status==='draft'?'草稿':'已发放' }}</el-tag></div>
        <div class="batch-form"><label>来源类型<el-select v-model="form.source_type"><el-option v-for="item in sourceOptions" :key="item.value" :label="item.label" :value="item.value"/></el-select></label><label>来源名称<el-input v-model="form.source_label" placeholder="如：七月热力榜"/></label><label>来源月份<el-date-picker v-model="form.source_month" type="month" value-format="YYYY-MM" placeholder="可选"/></label><label>发放日期<el-date-picker v-model="form.grant_date" type="date" value-format="YYYY-MM-DD"/></label><label>默认到期日<el-date-picker v-model="form.default_expiry" type="date" value-format="YYYY-MM-DD"/></label></div>
      </section>
      <section class="players-panel">
        <div class="section-heading"><div><h3>玩家与道具数量</h3><p>一行一个玩家；粘贴昵称后系统会自动匹配。</p></div><el-button type="primary" plain @click="pasteOpen=true">批量粘贴玩家</el-button></div>
        <el-table :data="rows" border empty-text="尚未添加玩家">
          <el-table-column label="玩家" fixed min-width="190"><template #default="{row}"><div class="player-cell"><strong>{{ row.playerName }}</strong><el-tag size="small" :type="row.status==='matched'?'success':row.status==='ambiguous'?'danger':'warning'">{{ row.status==='matched'?'已匹配':row.status==='ambiguous'?'重名待选':'待确认' }}</el-tag></div></template></el-table-column>
          <el-table-column v-for="item in activeDefinitions" :key="item.id" :label="item.display_name" min-width="140" align="center"><template #default="{row}"><el-input-number v-model="row.quantities[item.id]" :min="0" :max="100" :disabled="readOnly" controls-position="right"/></template></el-table-column>
          <el-table-column label="操作" width="90" fixed="right"><template #default="{$index}"><el-button link type="danger" :disabled="readOnly" @click="rows.splice($index,1)">移除</el-button></template></el-table-column>
        </el-table>
        <div class="summary"><span>{{ rows.length }} 位玩家</span><span>共 {{ totalItems }} 张道具</span><span v-if="unresolved" class="warning">{{ unresolved }} 位玩家待确认，暂不能发放</span></div>
      </section>
      <section class="history-panel"><div class="section-heading"><h3>发放批次</h3><div class="actions"><el-button :disabled="readOnly||busy||!rows.length" :loading="pending==='save'" @click="saveDraft">保存草稿</el-button><el-button type="primary" :disabled="readOnly||busy||!canConfirm" :loading="pending==='confirm'" @click="confirm">确认发放 {{ totalItems }} 张</el-button></div></div><div class="batch-list"><el-button v-for="item in batches" :key="item.id" size="small" :type="batch?.id===item.id?'primary':'default'" @click="openBatch(item)">{{ item.title||item.source_label }} · {{ item.status==='draft'?'草稿':'已发放' }}</el-button></div></section>
    </template>
    <el-dialog v-model="pasteOpen" title="批量添加玩家" width="min(560px, calc(100vw - 32px))" class="app-dialog"><el-input v-model="pastedNames" type="textarea" :rows="10" placeholder="每行一个玩家昵称\n例如：\n小A\nJennifer\nKiki"/><template #footer><el-button @click="pasteOpen=false">取消</el-button><el-button type="primary" :loading="pending==='match'" @click="matchPlayers">匹配并添加</el-button></template></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { EntitlementItemType, GrantBatch } from "../../features/entitlements/types";
import { createGrantRow, expandGrantItems, parsePastedPlayerNames, type GrantPlayerRow } from "../../features/entitlements/grant-table";
import { toIsoEndOfDay } from "../../features/entitlements/format";
import { confirmAction } from "../../features/dialogs/confirm-action";
const props=defineProps<{theaterId:number;definitions:EntitlementItemType[]}>(),auth=useAuthStore();
const rows=reactive<GrantPlayerRow[]>([]),batches=ref<GrantBatch[]>([]),batch=ref<GrantBatch|null>(null),pasteOpen=ref(false),pastedNames=ref(""),pending=ref<""|"load"|"match"|"save"|"confirm">("");
const form=reactive({source_type:"monthly_ranking",source_label:"",source_month:"",grant_date:new Date().toISOString().slice(0,10),default_expiry:""});
const sourceOptions=[{value:"monthly_ranking",label:"月度榜单"},{value:"campaign",label:"活动发放"},{value:"reissue",label:"补发"},{value:"manual_adjustment",label:"人工调整"},{value:"other",label:"其他"}];
const activeDefinitions=computed(()=>props.definitions.filter(item=>item.is_active)),readOnly=computed(()=>!!batch.value&&batch.value.status!=="draft"),busy=computed(()=>!!pending.value),totalItems=computed(()=>rows.reduce((sum,row)=>sum+Object.values(row.quantities).reduce((a,b)=>a+(Number(b)||0),0),0)),unresolved=computed(()=>rows.filter(row=>row.status!=="matched").length),canConfirm=computed(()=>totalItems.value>0&&!unresolved.value&&!!form.source_label.trim());
onMounted(load);watch(()=>props.theaterId,()=>{rows.splice(0);batch.value=null;void load()});
async function load(){if(!auth.token)return;pending.value="load";try{batches.value=await adminApi.getTheaterGrantBatches(auth.token,props.theaterId)}catch(e:any){ElMessage.error(e.message)}finally{pending.value=""}}
async function matchPlayers(){if(!auth.token)return;const names=parsePastedPlayerNames(pastedNames.value);if(!names.length)return ElMessage.warning("请粘贴至少一个玩家昵称");pending.value="match";try{const matches=await adminApi.matchEntitlementGrantPlayers(auth.token,props.theaterId,names);for(const result of matches){const row=createGrantRow(result.raw_name,activeDefinitions.value);if(result.player){row.playerId=result.player.id;row.playerName=result.player.display_name;row.status=result.player.status==="active"?"matched":"pending"}else if(result.candidates.length>1){row.status="ambiguous"}rows.push(row)}pasteOpen.value=false;pastedNames.value=""}catch(e:any){ElMessage.error(e.message)}finally{pending.value=""}}
function payload(){return {source_type:form.source_type,source_month:form.source_month?`${form.source_month}-01`:null,source_label:form.source_label.trim(),title:form.source_label.trim(),grant_date:form.grant_date||null,default_expires_at:toIsoEndOfDay(form.default_expiry),notes:null,items:expandGrantItems(rows,form.source_month?`${form.source_month}-01`:null,form.source_label.trim(),toIsoEndOfDay(form.default_expiry))}}
async function persist(){if(!auth.token)return null;const next=batch.value?await adminApi.updateGrantBatch(auth.token,batch.value.id,payload()):await adminApi.createTheaterGrantBatch(auth.token,props.theaterId,payload());batch.value=next;batches.value=[next,...batches.value.filter(item=>item.id!==next.id)];return next}
async function saveDraft(){pending.value="save";try{await persist();ElMessage.success("发放草稿已保存")}catch(e:any){ElMessage.error(e.message)}finally{pending.value=""}}
async function confirm(){if(!auth.token||!canConfirm.value)return;await confirmAction({title:"确认权益发放",message:`将向 ${rows.length} 位玩家发放 ${totalItems.value} 张道具，确认后不可修改。`,tone:"warning",confirmButtonText:"确认发放"});pending.value="confirm";try{const saved=await persist();if(saved){batch.value=await adminApi.confirmTheaterGrantBatch(auth.token,props.theaterId,saved.id,`grant-${saved.id}-${Date.now()}`);ElMessage.success("权益已发放");await load()}}catch(e:any){ElMessage.error(e.message)}finally{pending.value=""}}
function openBatch(item:GrantBatch){batch.value=item;form.source_type=item.source_type||"other";form.source_label=item.source_label;form.source_month=item.source_month?.slice(0,7)||"";form.grant_date=item.grant_date||"";form.default_expiry=item.default_expires_at?.slice(0,10)||"";rows.splice(0);const byPlayer=new Map<number,GrantPlayerRow>();for(const draft of item.draft_items){let row=byPlayer.get(draft.player_id);if(!row){row=createGrantRow(`玩家 #${draft.player_id}`,props.definitions);row.playerId=draft.player_id;row.status="matched";byPlayer.set(draft.player_id,row);rows.push(row)}row.quantities[draft.item_type_id]=(row.quantities[draft.item_type_id]||0)+1}}
</script>
<style scoped>
.grant-workspace{display:grid;gap:18px}.batch-panel,.players-panel,.history-panel,.empty-panel{background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px;padding:22px}.section-heading,.summary,.actions{display:flex;align-items:center;justify-content:space-between;gap:14px}.section-heading h2,.section-heading h3,.section-heading p{margin:0}.section-heading p{margin-top:6px;color:var(--el-text-color-secondary)}.batch-form{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:14px;margin-top:20px}.batch-form label{display:grid;gap:7px;color:var(--el-text-color-secondary);font-size:13px}.players-panel .el-table{margin-top:18px}.player-cell{display:flex;align-items:center;justify-content:space-between;gap:8px}.summary{justify-content:flex-start;margin-top:14px;color:var(--el-text-color-secondary)}.warning{color:var(--el-color-warning)}.batch-list{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}@media(max-width:1100px){.batch-form{grid-template-columns:repeat(2,1fr)}}
</style>
