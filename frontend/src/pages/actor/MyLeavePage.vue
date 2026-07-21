<template>
  <section class="leave-page">
    <span class="eyebrow">我的请假</span><h1>请假申请</h1>
    <p class="intro">按剧场选择一个或多个日期，每个日期可独立审批。</p>

    <div class="leave-form">
      <label>请假剧场 <b>必填</b></label>
      <el-select v-model="theaterId" placeholder="请选择剧场" size="large">
        <el-option v-for="row in theaters" :key="row.id" :label="row.name" :value="row.id" />
      </el-select>
      <label>请假日期 <b>必填</b></label>
      <el-date-picker v-model="dates" type="dates" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" placeholder="选择一个或多个日期" :disabled-date="disablePast" size="large" />
      <div v-if="dates.length" class="date-chips"><el-tag v-for="day in sortedDates" :key="day" closable @close="removeDate(day)">{{ formatDate(day) }}</el-tag></div>
      <label>申请备注</label>
      <el-input v-model="note" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="简单说明请假原因（可选）" />
      <el-button type="primary" size="large" :loading="submitting" :disabled="!theaterId || !dates.length" @click="submit">提交请假</el-button>
    </div>

    <div class="history-title"><h2>申请记录</h2><span>{{ applications.length }} 份</span></div>
    <article v-for="application in applications" :key="application.id" class="application-card">
      <header><div><strong>{{ application.theater_name }}</strong><small>{{ formatDateTime(application.created_at) }}</small></div><el-tag :type="overallType(application)">{{ overallLabel(application) }}</el-tag></header>
      <p v-if="application.note">{{ application.note }}</p>
      <div v-for="day in application.days" :key="day.id" class="day-row">
        <div><strong>{{ formatDate(day.leave_date) }}</strong><span v-if="day.has_schedule_conflict" class="conflict">存在排班冲突</span><small v-if="day.review_reason">{{ day.review_reason }}</small></div>
        <div class="day-action"><span :class="`status-${day.status}`">{{ statusLabel[day.status] }}</span><el-button v-if="day.status === 'pending'" text type="danger" @click="withdraw(day.id)">撤回</el-button></div>
      </div>
    </article>
    <el-empty v-if="!loading && !applications.length" description="暂无请假记录" :image-size="70" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"; import { ElMessage } from "element-plus";
import { actorApi, type LeaveApplication } from "../../api/admin"; import { useAuthStore } from "../../auth/store";
import { confirmAction } from "../../features/dialogs/confirm-action";
const auth=useAuthStore(); const theaterId=ref<number>(); const theaters=ref<{id:number;name:string}[]>([]); const dates=ref<string[]>([]); const note=ref(""); const applications=ref<LeaveApplication[]>([]); const submitting=ref(false); const loading=ref(false);
const statusLabel:Record<string,string>={pending:"待审批",approved:"已批准",rejected:"已驳回",withdrawn:"已撤回"}; const sortedDates=computed(()=>[...dates.value].sort());
const disablePast=(date:Date)=>date.getTime()<new Date(new Date().setHours(0,0,0,0)).getTime(); const formatDate=(v:string)=>{const [y,m,d]=v.slice(0,10).split("-");return `${y}年${Number(m)}月${Number(d)}日`}; const formatDateTime=(v:string)=>new Date(v).toLocaleString("zh-CN",{hour12:false});
function removeDate(day:string){dates.value=dates.value.filter(v=>v!==day)}
async function load(){if(!auth.token)return;loading.value=true;try{applications.value=await actorApi.getLeaveApplications(auth.token)}finally{loading.value=false}}
async function submit(){if(!auth.token||!theaterId.value)return;submitting.value=true;try{const row=await actorApi.submitLeaveApplication(auth.token,{theater_id:theaterId.value,dates:sortedDates.value,note:note.value||null});applications.value.unshift(row);dates.value=[];note.value="";ElMessage.success(row.days.some(v=>v.has_schedule_conflict)?"申请已提交，部分日期存在排班冲突":"请假申请已提交")}catch(e:any){ElMessage.error(e.message||"提交失败")}finally{submitting.value=false}}
async function withdraw(id:number){if(!auth.token)return;try{await confirmAction({title:"确认撤回该日期？",message:"撤回后如需请假须重新提交。",tone:"warning",confirmButtonText:"确认撤回"});await actorApi.withdrawLeaveDay(auth.token,id);await load();ElMessage.success("已撤回")}catch(e:any){if(e!=="cancel"&&e!=="close")ElMessage.error(e.message||"撤回失败")}}
function overallLabel(row:LeaveApplication){const active=row.days.filter(v=>v.status!=="withdrawn");if(active.some(v=>v.status==="pending"))return "审批中";if(active.length&&active.every(v=>v.status==="approved"))return "已批准";if(active.some(v=>v.status==="approved"))return "部分批准";return "已结束"} function overallType(row:LeaveApplication):any{return overallLabel(row)==="已批准"?"success":overallLabel(row)==="审批中"?"warning":"info"}
onMounted(async()=>{if(!auth.token)return;try{const profile=await actorApi.getProfile(auth.token);theaters.value=profile.theaters;theaterId.value=theaters.value[0]?.id}catch{}await load()});
</script>
<style scoped>
.leave-page{color:#182236}.eyebrow{color:#2f6fed;font-size:12px;font-weight:700}.leave-page h1{margin:5px 0 4px;font-size:27px}.intro{margin:0 0 18px;color:#7b8799;font-size:13px}.leave-form{display:grid;gap:10px;padding:18px;background:#fff;border:1px solid #e1e8f2;border-radius:18px}.leave-form label{margin-top:3px;font-size:13px;font-weight:600}.leave-form label b{margin-left:4px;color:#e5484d;font-size:10px}.leave-form :deep(.el-date-editor){width:100%}.date-chips{display:flex;gap:6px;flex-wrap:wrap}.history-title{display:flex;align-items:center;justify-content:space-between;margin:22px 2px 10px}.history-title h2{margin:0;font-size:18px}.history-title span{color:#98a2b3;font-size:12px}.application-card{padding:16px;margin-bottom:12px;background:#fff;border:1px solid #e1e8f2;border-radius:18px}.application-card header{display:flex;justify-content:space-between}.application-card header div{display:flex;flex-direction:column;gap:3px}.application-card small{color:#98a2b3;font-size:11px}.application-card>p{padding:9px 11px;background:#f7f9fc;border-radius:10px;color:#667085;font-size:12px}.day-row{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-top:1px solid #edf0f5}.day-row>div:first-child{display:flex;flex-direction:column;gap:3px}.day-row strong{font-size:13px}.conflict{color:#d97706;font-size:11px}.day-action{display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600}.status-pending{color:#d97706}.status-approved{color:#15945f}.status-rejected{color:#d9383a}.status-withdrawn{color:#98a2b3}
</style>
