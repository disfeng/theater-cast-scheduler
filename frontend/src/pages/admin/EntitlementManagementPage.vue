<template>
  <section class="page-container">
    <PageHeader title="权益管理" description="按剧场配置道具、批量发放权益，并追踪每一张道具的背包与流水。" />
    <div class="theater-context theater-context--compact">
      <div class="theater-context__label"><span>当前剧场</span><strong>{{ currentTheater?.name || "请选择剧场" }}</strong></div>
      <el-select v-model="theaterId" placeholder="请选择剧场" aria-label="当前剧场" @change="syncTheater"><el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id"/></el-select>
    </div>
    <el-tabs v-model="activeTab" class="entitlement-tabs" @tab-change="syncTabQuery">
      <el-tab-pane label="道具配置" name="catalog" lazy><ItemCatalogTab v-if="theaterId" :theater-id="theaterId" :definitions="definitions" :loading="loading" @refresh="loadDefinitions" /></el-tab-pane>
      <el-tab-pane label="权益发放" name="grants" lazy><GrantBatchTab v-if="theaterId" :theater-id="theaterId" :definitions="definitions" /></el-tab-pane>
      <el-tab-pane label="权益背包" name="inventory" lazy><PlayerInventoryTab v-if="theaterId" :theater-id="theaterId" :definitions="definitions" @open-ledger="openLedger" /></el-tab-pane>
      <el-tab-pane label="权益流水" name="ledger" lazy><EntitlementLedgerTab v-if="theaterId" :theater-id="theaterId" :definitions="definitions" /></el-tab-pane>
    </el-tabs>
    <el-empty v-if="!loadingTheaters && !theaterId" description="请先选择一个剧场开始管理权益" />
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { adminApi, type Theater } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { EntitlementItemType } from "../../features/entitlements/types";
import ItemCatalogTab from "../../components/admin/ItemCatalogTab.vue";
import GrantBatchTab from "../../components/admin/GrantBatchTab.vue";
import PlayerInventoryTab from "../../components/admin/PlayerInventoryTab.vue";
import EntitlementLedgerTab from "../../components/admin/EntitlementLedgerTab.vue";
import PageHeader from "../../components/PageHeader.vue";
const route=useRoute(),router=useRouter(),auth=useAuthStore();
const allowedTabs=new Set(["catalog","grants","inventory","ledger"]), activeTab=ref(typeof route.query.tab==="string"&&allowedTabs.has(route.query.tab)?route.query.tab:"catalog");
const theaters=ref<Theater[]>([]), theaterId=ref<number|null>(Number(route.query.theater_id)||null), definitions=ref<EntitlementItemType[]>([]),loading=ref(false),loadingTheaters=ref(true);
const currentTheater=computed(()=>theaters.value.find(i=>i.id===theaterId.value));
onMounted(async()=>{if(!auth.token)return;try{theaters.value=await adminApi.getTheaters(auth.token);if(!theaterId.value&&theaters.value.length) theaterId.value=theaters.value[0].id;if(theaterId.value) await loadDefinitions();syncRoute();}catch(e:any){ElMessage.error(e.message)}finally{loadingTheaters.value=false}});
watch(()=>route.query.tab,t=>{if(typeof t==="string"&&allowedTabs.has(t))activeTab.value=t});
async function loadDefinitions(){if(!auth.token||!theaterId.value)return;loading.value=true;try{definitions.value=await adminApi.getTheaterEntitlementItemTypes(auth.token,theaterId.value)}catch(e:any){ElMessage.error(e.message)}finally{loading.value=false}}
async function syncTheater(){await loadDefinitions();syncRoute()}
function syncTabQuery(tab:string|number){activeTab.value=String(tab);syncRoute()}
function syncRoute(extra:Record<string,string>={}){void router.replace({query:{...route.query,...extra,tab:activeTab.value,...(theaterId.value?{theater_id:String(theaterId.value)}:{})}})}
function openLedger(filters:{playerId:number;itemId:number}){activeTab.value="ledger";syncRoute({player_id:String(filters.playerId),item_id:String(filters.itemId)})}
</script>
<style scoped>
.theater-context{display:flex;align-items:center;gap:18px;padding:12px 16px;margin-bottom:14px;background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:12px}.theater-context__label{display:flex;align-items:baseline;gap:10px;white-space:nowrap}.theater-context span{font-size:13px;color:var(--el-text-color-secondary)}.theater-context .el-select{width:min(300px,36vw);margin-left:auto}.entitlement-tabs :deep(.el-tabs__content){padding-top:10px}@media(max-width:700px){.theater-context{align-items:stretch;flex-wrap:wrap}.theater-context__label{width:100%}.theater-context .el-select{width:100%;margin-left:0}}
</style>
