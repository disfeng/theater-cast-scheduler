<template>
  <section class="page-container">
    <PageHeader title="请假审核" description="按申请单查看请假，并对每个日期独立批准或驳回。" />
    <div class="toolbar panel">
      <div class="filter-grid">
        <el-select v-model="theaterId" placeholder="请选择剧场" @change="onTheaterChange"><el-option v-for="row in theaters" :key="row.id" :label="row.name" :value="row.id" /></el-select>
        <el-input v-model="keyword" clearable placeholder="搜索演员或备注" />
        <el-select v-model="actorName" clearable placeholder="筛选演员"><el-option v-for="name in actorOptions" :key="name" :label="name" :value="name" /></el-select>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至" />
      </div>
      <div class="pending-summary"><strong>{{ pendingCount }}</strong><span>个日期待审批</span></div>
    </div>
    <div class="request-list">
      <article v-for="application in filteredApplications" :key="application.id" class="request-row" role="region" :aria-label="`${application.actor_name}的请假申请`">
        <div class="request-person"><div class="actor-avatar">{{ application.actor_name.slice(0,1) }}</div><div class="request-title"><h3>{{ application.actor_name }}</h3><p>{{ formatDateTime(application.created_at) }} 提交</p></div></div>
        <p class="note"><span>备注</span>{{ application.note || "未填写" }}</p>
        <div class="day-list date-actions-grid">
          <div v-for="day in application.days" :key="day.id" class="day-item">
            <div class="day-meta"><strong>{{ formatDate(day.leave_date) }}</strong><span v-if="day.has_schedule_conflict" class="conflict-dot">需调整排班</span><small v-if="day.review_reason">{{ day.review_reason }}</small></div>
            <div v-if="day.status==='pending'" class="actions"><el-button size="small" type="success" plain :aria-label="`批准${shortDate(day.leave_date)}`" @click="review(day.id,'approved')">批准</el-button><el-button size="small" type="danger" text :aria-label="`驳回${shortDate(day.leave_date)}`" @click="review(day.id,'rejected')">驳回</el-button></div>
            <span v-else :class="`status status-${day.status}`">{{ statusLabel[day.status] }}</span>
          </div>
        </div>
        <div v-if="application.days.filter(v=>v.status==='pending').length>1" class="batch-actions"><el-button size="small" @click="reviewAll(application,'approved')">全部批准</el-button><el-button size="small" type="danger" plain @click="reviewAll(application,'rejected')">全部驳回</el-button></div>
      </article>
    </div>
    <el-empty v-if="!loading&&!filteredApplications.length" description="没有符合条件的请假申请" />
  </section>
</template>
<script setup lang="ts">
import { computed,onMounted,ref } from "vue";import{ElMessage,ElMessageBox}from"element-plus";import PageHeader from"../../components/PageHeader.vue";import{adminApi,type LeaveApplication,type Theater}from"../../api/admin";import{useAuthStore}from"../../auth/store";import{confirmAction}from"../../features/dialogs/confirm-action";
const auth=useAuthStore();const applications=ref<LeaveApplication[]>([]);const theaters=ref<Theater[]>([]);const theaterId=ref<number>();const loading=ref(false);const keyword=ref("");const actorName=ref("");const dateRange=ref<string[]>([]);const statusLabel:Record<string,string>={approved:"已批准",rejected:"已驳回",withdrawn:"已撤回",pending:"待审批"};
const actorOptions=computed(()=>[...new Set(applications.value.map(v=>v.actor_name))].sort((a,b)=>a.localeCompare(b,"zh-CN")));
const filteredApplications=computed(()=>{const text=keyword.value.trim().toLowerCase();return applications.value.map(row=>({...row,days:row.days.filter(day=>!dateRange.value?.length||(day.leave_date>=dateRange.value[0]&&day.leave_date<=dateRange.value[1]))})).filter(row=>row.days.length&&(!actorName.value||row.actor_name===actorName.value)&&(!text||row.actor_name.toLowerCase().includes(text)||(row.note||"").toLowerCase().includes(text)))});
const pendingCount=computed(()=>filteredApplications.value.flatMap(v=>v.days).filter(v=>v.status==="pending").length);
const formatDate=(v:string)=>{const[,m,d]=v.split("-");return `${Number(m)}月${Number(d)}日`};const shortDate=formatDate;const formatDateTime=(v:string)=>new Date(v).toLocaleDateString("zh-CN");
async function load(){if(!auth.token)return;loading.value=true;try{applications.value=await adminApi.getLeaveApplications(auth.token,theaterId.value)}catch(e:any){ElMessage.error(e.message||"加载失败")}finally{loading.value=false}}
async function onTheaterChange(){keyword.value="";actorName.value="";dateRange.value=[];await load()}
async function askReason(){return ElMessageBox.prompt("请填写明确的驳回理由，演员端会展示该内容。","填写驳回理由",{customClass:"app-message-box app-message-box--danger",confirmButtonText:"确认驳回",cancelButtonText:"取消",inputPlaceholder:"请输入驳回理由",inputValidator:v=>Boolean(v.trim())||"驳回理由不能为空"}).then(v=>v.value)}
async function review(id:number,status:"approved"|"rejected"){if(!auth.token)return;try{const reason=status==="rejected"?await askReason():null;await adminApi.reviewLeaveApplicationDay(auth.token,id,status,reason);await load();ElMessage.success(status==="approved"?"已批准":"已驳回")}catch(e:any){if(e!=="cancel"&&e!=="close")ElMessage.error(e.message||"审批失败")}}
async function reviewAll(row:LeaveApplication,status:"approved"|"rejected"){if(!auth.token)return;try{const reason=status==="rejected"?await askReason():null;if(status==="approved")await confirmAction({title:`确认批准 ${row.actor_name} 的请假？`,message:`将批准 ${row.days.filter(v=>v.status==='pending').length} 个待审批日期。`,tone:"primary",confirmButtonText:"确认批准"});await adminApi.reviewPendingLeaveDays(auth.token,row.id,status,reason);await load();ElMessage.success("批量审批完成")}catch(e:any){if(e!=="cancel"&&e!=="close")ElMessage.error(e.message||"审批失败")}}
onMounted(async()=>{if(!auth.token)return;theaters.value=await adminApi.getTheaters(auth.token);theaterId.value=theaters.value[0]?.id;await load()});
</script>
<style scoped>
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 16px}.filter-grid{display:grid;grid-template-columns:220px 220px 180px 330px;gap:10px;min-width:0}.filter-grid :deep(.el-date-editor){width:100%}.pending-summary{display:flex;align-items:baseline;gap:6px;white-space:nowrap}.pending-summary strong{color:#2f6fed;font-size:23px}.pending-summary span{color:#7b8799;font-size:13px}.request-list{display:flex;flex-direction:column;gap:10px}.request-row{display:grid;grid-template-columns:210px 160px minmax(0,1fr) auto;align-items:center;gap:16px;padding:14px 16px;background:#fff;border:1px solid #dfe6ef;border-radius:14px;box-shadow:0 3px 12px rgba(38,53,79,.035)}.request-person{display:flex;align-items:center;gap:11px}.actor-avatar{display:grid;place-items:center;flex:0 0 38px;width:38px;height:38px;border-radius:12px;background:#edf4ff;color:#2f6fed;font-weight:700}.request-title h3{margin:0;font-size:16px}.request-title p{margin:3px 0 0;color:#98a2b3;font-size:11px}.note{display:flex;gap:8px;margin:0;color:#667085;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.note span{color:#98a2b3}.date-actions-grid{display:flex;flex-wrap:wrap;gap:8px}.day-item{display:flex;align-items:center;flex:1 1 205px;max-width:265px;min-height:44px;gap:8px;padding:6px 8px 6px 11px;background:#f8fafc;border:1px solid #e6ebf2;border-radius:10px}.day-meta{display:flex;align-items:center;gap:6px;min-width:0;flex:1}.day-item strong{font-size:13px;white-space:nowrap}.day-item small{color:#98a2b3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.conflict-dot{padding:2px 6px;border-radius:999px;background:#fff1d6;color:#d97706;font-size:10px;white-space:nowrap}.actions{display:flex;align-items:center;gap:0}.actions .el-button{padding-inline:7px}.status{padding:3px 7px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}.status-approved{background:#edf9f2;color:#15945f}.status-rejected{background:#fff0f0;color:#d9383a}.status-withdrawn{background:#f0f2f5;color:#98a2b3}.batch-actions{display:flex;justify-content:flex-end;gap:4px;padding-left:12px;border-left:1px solid #edf0f5}@media(max-width:1400px){.filter-grid{grid-template-columns:200px 190px 170px minmax(280px,1fr)}.request-row{grid-template-columns:190px 140px 1fr}.batch-actions{grid-column:1/-1;border-left:0;padding-top:8px;border-top:1px solid #edf0f5}.day-item{max-width:none}}@media(max-width:900px){.toolbar{align-items:stretch;flex-direction:column}.filter-grid{grid-template-columns:1fr 1fr}.pending-summary{justify-content:flex-end}}@media(max-width:760px){.filter-grid{grid-template-columns:1fr}.request-row{grid-template-columns:1fr;gap:10px}.note{padding:8px 10px;background:#f7f9fc;border-radius:9px}.day-item{flex-basis:100%;max-width:none}.batch-actions{grid-column:auto}}
</style>
