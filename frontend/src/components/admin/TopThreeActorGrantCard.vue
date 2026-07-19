<template>
  <article class="actor-card" data-testid="top-three-actor-card">
    <header>
      <div><span class="eyebrow">榜三指定</span><h3>榜三指定 · {{ actor.display_name }}</h3></div>
      <div class="header-actions"><el-tag v-if="batch" :type="batch.status==='draft'?'warning':'success'">{{ batch.status==='draft'?'草稿':'已发放' }}</el-tag><el-button :aria-label="`为${actor.display_name}粘贴玩家`" :disabled="readOnly" @click="pasteOpen=true">粘贴玩家</el-button></div>
    </header>
    <el-table :data="rows" border size="small" empty-text="尚未添加榜单玩家">
      <el-table-column label="玩家" min-width="240"><template #default="{row}"><div class="player-cell"><strong>{{ row.playerName }}</strong><el-tag size="small" :type="row.status==='matched'?'success':row.status==='ambiguous'?'danger':'warning'">{{ row.status==='matched'?'已匹配':row.status==='ambiguous'?'重名待选':'待确认' }}</el-tag><el-select v-if="row.status==='ambiguous'" v-model="row.playerId" size="small" :aria-label="`选择${row.rawName}对应玩家`" @change="selectCandidate(row,$event)"><el-option v-for="candidate in row.candidates" :key="candidate.id" :label="candidate.display_name" :value="candidate.id"/></el-select></div></template></el-table-column>
      <el-table-column label="榜三指定" width="180" align="center"><template #default="{row}"><el-input-number v-model="row.quantities[definition.id]" :min="0" :max="100" :disabled="readOnly" controls-position="right"/></template></el-table-column>
      <el-table-column label="操作" width="160" align="right"><template #default="{row,$index}"><el-button v-if="row.status==='pending'&&row.playerId" link type="primary" :disabled="readOnly" @click="confirmPlayer(row)">确认玩家</el-button><el-button link type="danger" :disabled="readOnly" @click="rows.splice($index,1)">移除</el-button></template></el-table-column>
    </el-table>
    <footer><span>{{ rows.length }} 位玩家 · {{ totalItems }} 张</span><span v-if="unresolved" class="warning">{{ unresolved }} 位待确认</span></footer>
    <el-dialog v-model="pasteOpen" :title="`添加${actor.display_name}的榜单玩家`" width="min(560px, calc(100vw - 32px))" class="app-dialog"><el-input v-model="pastedNames" type="textarea" :rows="9" placeholder="每行一个玩家昵称\n例如：\n玩家甲\n玩家乙"/><template #footer><el-button @click="pasteOpen=false">取消</el-button><el-button type="primary" :loading="pending==='match'" @click="matchPlayers">匹配并添加</el-button></template></el-dialog>
  </article>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { adminApi, type Actor } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { EntitlementItemType, GrantBatch, GrantBatchPayload } from "../../features/entitlements/types";
import { topThreeCardInvalidReason, type CardOperationResult, type TopThreeGrantDefaults } from "../../features/entitlements/top-three-grants";
import { applyGrantPlayerMatch, createGrantRow, expandGrantItems, grantRowIsResolved, parsePastedPlayerNames, type GrantPlayerRow } from "../../features/entitlements/grant-table";
import { toIsoEndOfDay } from "../../features/entitlements/format";
import { confirmAction } from "../../features/dialogs/confirm-action";

const props=defineProps<{actor:Actor;definition:EntitlementItemType;theaterId:number;defaults:TopThreeGrantDefaults;initialBatch?:GrantBatch|null}>();
const emit=defineEmits<{(event:"batch-change",batch:GrantBatch):void}>(),auth=useAuthStore();
const rows=reactive<GrantPlayerRow[]>([]),batch=ref<GrantBatch|null>(props.initialBatch??null),pasteOpen=ref(false),pastedNames=ref(""),pending=ref<""|"match"|"save"|"confirm">("");
if(props.initialBatch){const byPlayer=new Map<number,GrantPlayerRow>();for(const draft of props.initialBatch.draft_items){let row=byPlayer.get(draft.player_id);if(!row){row=createGrantRow(`玩家 #${draft.player_id}`,[props.definition]);row.playerId=draft.player_id;row.status="matched";byPlayer.set(draft.player_id,row);rows.push(row)}row.quantities[props.definition.id]=(row.quantities[props.definition.id]||0)+(draft.quantity||1)}}
const readOnly=computed(()=>batch.value?.status==="granted"),totalItems=computed(()=>rows.reduce((sum,row)=>sum+(Number(row.quantities[props.definition.id])||0),0)),unresolved=computed(()=>rows.filter(row=>!grantRowIsResolved(row)).length),invalidReason=computed(()=>topThreeCardInvalidReason({sourceLabel:props.defaults.source_label,playerCount:rows.length,totalItems:totalItems.value,unresolved:unresolved.value}));
function hasContent(){return rows.length>0||!!batch.value}
function isValid(){return invalidReason.value===null}
async function matchPlayers(){if(!auth.token)return;const names=parsePastedPlayerNames(pastedNames.value);if(!names.length)return ElMessage.warning("请粘贴至少一个玩家昵称");pending.value="match";try{const matches=await adminApi.matchEntitlementGrantPlayers(auth.token,props.theaterId,names);for(const result of matches){const row=createGrantRow(result.raw_name,[props.definition]);applyGrantPlayerMatch(row,result);row.quantities[props.definition.id]=1;rows.push(row)}pasteOpen.value=false;pastedNames.value=""}catch(e:any){ElMessage.error(e.message)}finally{pending.value=""}}
function selectCandidate(row:GrantPlayerRow,playerId:number){const player=row.candidates.find(item=>item.id===playerId);if(!player)return;row.playerId=player.id;row.playerName=player.display_name;row.status=player.status==="active"?"matched":"pending"}
async function confirmPlayer(row:GrantPlayerRow){if(!auth.token||!row.playerId)return;await confirmAction({title:"确认玩家身份",message:`确认“${row.playerName}”为正式玩家后，即可向其发放权益。`,tone:"warning",confirmButtonText:"确认玩家身份"});try{const player=await adminApi.updatePlayerProfile(auth.token,row.playerId,{status:"active"});row.playerName=player.display_name;row.status="matched"}catch(e:any){ElMessage.error(e.message)}}
function payload():GrantBatchPayload{const label=`${props.defaults.source_label.trim()} · ${props.actor.display_name}`;const month=props.defaults.source_month?`${props.defaults.source_month}-01`:null;return {source_type:props.defaults.source_type,source_month:month,source_label:label,title:label,grant_date:props.defaults.grant_date||null,default_expires_at:toIsoEndOfDay(props.defaults.default_expiry),notes:null,bound_actor_id:props.actor.id,items:expandGrantItems(rows,month,label,toIsoEndOfDay(props.defaults.default_expiry),props.actor.id)}}
async function persist(){if(!auth.token)throw new Error("未登录");const next=batch.value?await adminApi.updateGrantBatch(auth.token,batch.value.id,payload()):await adminApi.createTheaterGrantBatch(auth.token,props.theaterId,payload());batch.value=next;emit("batch-change",next);return next}
async function saveDraft():Promise<CardOperationResult>{if(!hasContent())return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"skipped",reason:"未添加玩家"};pending.value="save";try{await persist();return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"saved"}}catch(e:any){return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"failed",reason:e.message}}finally{pending.value=""}}
async function confirmGrant():Promise<CardOperationResult>{if(invalidReason.value)return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"skipped",reason:invalidReason.value};pending.value="confirm";try{const saved=await persist();if(!auth.token)throw new Error("未登录");const next=await adminApi.confirmTheaterGrantBatch(auth.token,props.theaterId,saved.id,`grant-${saved.id}-${Date.now()}`);batch.value=next;emit("batch-change",next);return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"granted"}}catch(e:any){return {actorId:props.actor.id,actorName:props.actor.display_name,outcome:"failed",reason:e.message}}finally{pending.value=""}}
defineExpose({hasContent,isValid,saveDraft,confirmGrant});
</script>
<style scoped>
.actor-card{display:grid;gap:16px;padding:20px;border:1px solid #f3c9c9;border-left:4px solid #d94848;border-radius:14px;background:#fff}.actor-card header,.header-actions,.actor-card footer,.player-cell{display:flex;align-items:center;gap:10px}.actor-card header{justify-content:space-between}.actor-card h3{margin:3px 0 0;color:var(--el-text-color-primary)}.eyebrow{font-size:12px;font-weight:700;color:#c63737}.actor-card footer{color:var(--el-text-color-secondary);font-size:13px}.warning{color:var(--el-color-warning)}.player-cell{flex-wrap:wrap}.player-cell strong{margin-right:auto}
</style>
