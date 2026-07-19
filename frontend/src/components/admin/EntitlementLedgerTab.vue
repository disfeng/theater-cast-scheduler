<template>
  <div class="ledger-workspace">
    <div class="ledger-header"><div><h2>权益流水</h2><p>当前剧场全部道具变化的不可变审计记录。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <div class="filters"><el-input v-model="playerQuery" clearable placeholder="搜索玩家" aria-label="流水玩家" @keyup.enter="searchPlayer"/><el-select v-model="filters.item_type_id" clearable placeholder="全部道具" @change="load"><el-option v-for="item in definitions" :key="item.id" :label="item.display_name" :value="item.id"/></el-select><el-select v-model="filters.event_type" clearable placeholder="全部事件" @change="load"><el-option v-for="item in events" :key="item.value" :label="item.label" :value="item.value"/></el-select><el-button type="primary" @click="searchPlayer">查询</el-button></div>
    <div v-if="selectedPlayer" class="active-filter">玩家：{{ selectedPlayer.display_name }}<el-button link @click="clearPlayer">清除</el-button></div>
    <el-table v-loading="loading" :data="page.records" stripe empty-text="当前筛选下暂无流水">
      <el-table-column label="发生时间" min-width="160"><template #default="{row}">{{ formatEntitlementDate(row.occurred_at) }}</template></el-table-column><el-table-column prop="player_name" label="玩家" min-width="110"/><el-table-column prop="item_type_name" label="道具" min-width="130"/><el-table-column prop="serial_number" label="序列号" min-width="170"/><el-table-column label="事件" width="110"><template #default="{row}"><el-tag effect="plain">{{ entitlementLabel(row.event_type) }}</el-tag></template></el-table-column><el-table-column label="状态变化" min-width="150"><template #default="{row}">{{ entitlementLabel(row.from_status || 'none') }} → {{ entitlementLabel(row.to_status || 'none') }}</template></el-table-column><el-table-column label="用途 / 原因" min-width="190"><template #default="{row}">{{ row.purpose || row.reason || row.note || '—' }}</template></el-table-column>
    </el-table>
    <div class="pagination"><el-button v-if="page.next_cursor" :loading="loading" @click="loadMore">加载更多</el-button></div>
  </div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { EntitlementItemType, EntitlementLedgerPage, PlayerProfile } from "../../features/entitlements/types";
import { entitlementLabel, formatEntitlementDate } from "../../features/entitlements/format";
const props=defineProps<{theaterId:number;definitions:EntitlementItemType[]}>(),auth=useAuthStore(),route=useRoute();
const loading=ref(false),playerQuery=ref(""),selectedPlayer=ref<PlayerProfile|null>(null),page=ref<EntitlementLedgerPage>({records:[],next_cursor:null}),filters=reactive<{player_id?:number;item_type_id?:number;event_type?:string;item_id?:number}>({player_id:Number(route.query.player_id)||undefined,item_id:Number(route.query.item_id)||undefined});
const events=["granted","reserved","released","consumed","manually_consumed","expired","revoked","extended","restored","adjusted"].map(value=>({value,label:entitlementLabel(value)}));
onMounted(load);watch(()=>props.theaterId,()=>{page.value={records:[],next_cursor:null};void load()});
async function load(){if(!auth.token)return;loading.value=true;try{page.value=await adminApi.getEntitlementLedger(auth.token,props.theaterId,filters)}catch(e:any){ElMessage.error(e.message)}finally{loading.value=false}}
async function loadMore(){if(!page.value.next_cursor||!auth.token)return;loading.value=true;try{const next=await adminApi.getEntitlementLedger(auth.token,props.theaterId,{...filters,cursor:page.value.next_cursor});page.value={records:[...page.value.records,...next.records],next_cursor:next.next_cursor}}catch(e:any){ElMessage.error(e.message)}finally{loading.value=false}}
async function searchPlayer(){if(!auth.token)return;if(!playerQuery.value.trim()){filters.player_id=undefined;selectedPlayer.value=null;return load()}try{const rows=await adminApi.getPlayerProfiles(auth.token,playerQuery.value.trim());if(rows.length!==1)return ElMessage.warning(rows.length?"找到多个玩家，请输入更准确的昵称":"未找到玩家");selectedPlayer.value=rows[0];filters.player_id=rows[0].id;await load()}catch(e:any){ElMessage.error(e.message)}}
function clearPlayer(){selectedPlayer.value=null;playerQuery.value="";filters.player_id=undefined;void load()}
</script>
<style scoped>
.ledger-workspace{background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px;padding:22px}.ledger-header,.active-filter{display:flex;justify-content:space-between;align-items:center}.ledger-header h2,.ledger-header p{margin:0}.ledger-header p{margin-top:6px;color:var(--el-text-color-secondary)}.filters{display:grid;grid-template-columns:minmax(180px,1fr) minmax(160px,220px) minmax(150px,200px) auto;gap:12px;margin:22px 0}.active-filter{justify-content:flex-start;gap:8px;margin-bottom:12px;color:var(--el-color-primary)}.pagination{text-align:center;margin-top:18px}@media(max-width:760px){.filters{grid-template-columns:1fr 1fr}}
</style>
