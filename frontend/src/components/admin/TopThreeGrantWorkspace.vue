<template>
  <section class="workspace">
    <div class="toolbar"><div class="actor-picker"><span>榜单演员</span><el-select v-model="selectedIds" multiple filterable collapse-tags :max-collapse-tags="3" aria-label="榜单演员" placeholder="选择一个或多个演员" @remove-tag="protectRemoval"><el-option v-for="actor in actors" :key="actor.id" :label="actor.display_name" :value="actor.id"/></el-select></div><div class="quick-actions"><el-button @click="selectedIds=actors.map(item=>item.id)">选择全部演员</el-button><el-button @click="clearSelection">清空选择</el-button></div></div>
    <el-empty v-if="!selectedActors.length" description="请选择榜单演员后分别粘贴玩家" />
    <div v-else class="cards"><TopThreeActorGrantCard v-for="actor in selectedActors" :key="actor.id" :ref="instance=>setCardRef(actor.id,instance)" :actor="actor" :definition="definition" :theater-id="theaterId" :defaults="defaults" :initial-batch="latestBatch(actor.id)" @batch-change="updateBatch"/></div>
    <div v-if="selectedActors.length" class="bulk-actions"><el-button :loading="bulkPending" @click="runBulk('saveDraft')">保存全部草稿</el-button><el-button type="primary" :loading="bulkPending" @click="runBulk('confirmGrant')">发放全部有效 Card</el-button></div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import type { Actor } from "../../api/admin";
import type { EntitlementItemType, GrantBatch } from "../../features/entitlements/types";
import { summarizeCardResults, type CardOperationResult, type TopThreeActorCardExpose, type TopThreeGrantDefaults } from "../../features/entitlements/top-three-grants";
import { confirmAction } from "../../features/dialogs/confirm-action";
import TopThreeActorGrantCard from "./TopThreeActorGrantCard.vue";
const props=defineProps<{theaterId:number;actors:Actor[];definition:EntitlementItemType;defaults:TopThreeGrantDefaults;batches:GrantBatch[]}>();
const emit=defineEmits<{(event:"batch-change",batch:GrantBatch):void}>();
const selectedIds=ref<number[]>([...new Set(props.batches.filter(item=>item.bound_actor_id).map(item=>item.bound_actor_id!))]),cardRefs=new Map<number,TopThreeActorCardExpose>(),bulkPending=ref(false);
const selectedActors=computed(()=>selectedIds.value.map(id=>props.actors.find(actor=>actor.id===id)).filter((actor):actor is Actor=>!!actor));
function setCardRef(id:number,instance:any){if(instance)cardRefs.set(id,instance);else cardRefs.delete(id)}
function latestBatch(actorId:number){return props.batches.find(item=>item.bound_actor_id===actorId)??null}
function updateBatch(batch:GrantBatch){emit("batch-change",batch)}
async function protectRemoval(actorId:number){const card=cardRefs.get(actorId);if(!card?.hasContent())return;try{await confirmAction({title:"移除演员发放卡",message:"该演员卡已包含玩家或草稿，移除后当前页面中的未保存编辑将丢失。",tone:"warning",confirmButtonText:"确认移除"})}catch{selectedIds.value=[...selectedIds.value,actorId]}}
async function clearSelection(){const protectedIds=selectedIds.value.filter(id=>cardRefs.get(id)?.hasContent());if(protectedIds.length){try{await confirmAction({title:"清空演员发放卡",message:`${protectedIds.length} 张演员卡已包含玩家或草稿，确认清空吗？`,tone:"warning",confirmButtonText:"确认清空"})}catch{return}}selectedIds.value=[]}
async function runBulk(method:"saveDraft"|"confirmGrant"){bulkPending.value=true;const results:CardOperationResult[]=[];try{for(const actor of selectedActors.value){const card=cardRefs.get(actor.id);if(card)results.push(await card[method]())}const summary=summarizeCardResults(results);await confirmAction({alert:true,title:method==="confirmGrant"?"批量发放结果":"批量保存结果",message:[summary.successful.length?`成功：${summary.successful.join("、")}`:"",summary.skipped.length?`跳过：${summary.skipped.join("、")}`:"",summary.failed.length?`失败：${summary.failed.join("、")}`:""].filter(Boolean).join("\n"),tone:summary.failed.length?"warning":"primary",confirmButtonText:"知道了"})}catch{ElMessage.info("已取消")}finally{bulkPending.value=false}}
</script>
<style scoped>
.workspace{display:grid;gap:18px}.toolbar,.actor-picker,.quick-actions,.bulk-actions{display:flex;align-items:center;gap:12px}.toolbar{justify-content:space-between;padding:16px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:var(--el-fill-color-lighter)}.actor-picker{flex:1;color:var(--el-text-color-secondary);font-weight:600}.actor-picker .el-select{width:min(620px,75%)}.cards{display:grid;gap:14px}.bulk-actions{justify-content:flex-end;position:sticky;bottom:12px;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:rgba(255,255,255,.94);box-shadow:0 8px 24px rgba(31,45,61,.08)}
</style>
