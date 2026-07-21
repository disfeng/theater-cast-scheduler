<template>
  <el-dialog :model-value="modelValue" title="修订登记信息" width="min(620px, calc(100vw - 32px))" class="app-dialog correction-dialog" append-to-body :close-on-click-modal="false" @close="close">
    <div v-if="target" class="correction-body">
      <el-alert title="修订不会覆盖原记录，系统会保存新版本和操作原因。" type="info" :closable="false" show-icon />
      <div class="form-grid">
        <label>玩家昵称<el-input v-model="form.player_name" :disabled="immutable('player_name')" /></label>
        <label>演员<el-select v-model="form.actor_id" filterable :disabled="immutable('actor_id')"><el-option v-for="actor in actors" :key="actor.id" :label="actor.display_name" :value="actor.id" /></el-select></label>
        <label>角色<el-select v-model="form.role_id" filterable :disabled="immutable('role_id')"><el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" /></el-select></label>
      </div>
      <label>备注<el-input v-model="form.note" type="textarea" :rows="2" /></label>
      <label>修订原因 <span class="required">必填</span><el-input v-model="form.reason" type="textarea" :rows="3" placeholder="例如：微信群登记昵称有误，经客服核实后修正" /></label>
      <div v-if="preview" class="preview-box"><strong>修订影响预览</strong><span>{{ previewText }}</span><small v-if="preview.immutable_fields.length">演出完成后不可修改：{{ preview.immutable_fields.join('、') }}</small></div>
    </div>
    <template #footer><el-button @click="close">取消</el-button><el-button :loading="busy" :disabled="!form.reason.trim()" @click="loadPreview">预览修订</el-button><el-button type="primary" :loading="busy" :disabled="!preview || !form.reason.trim()" @click="submit">确认修订</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { adminApi, type BusinessCorrectionPreview, type PerformanceWish, type Predesignation } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import { confirmAction } from "../../features/dialogs/confirm-action";
const props=defineProps<{modelValue:boolean;kind:"designation"|"wish";target:Predesignation|PerformanceWish|null;theaterId:number}>();
const emit=defineEmits<{"update:modelValue":[boolean];changed:[]}>();
const auth=useAuthStore(),actors=ref<any[]>([]),roles=ref<any[]>([]),preview=ref<BusinessCorrectionPreview|null>(null),busy=ref(false);
const form=reactive({player_name:"",actor_id:0,role_id:0,note:"",reason:""});
watch(()=>[props.modelValue,props.target] as const,async([open,target])=>{if(!open||!target)return;Object.assign(form,{player_name:props.kind==="designation"?(target as Predesignation).beneficiary_name:(target as PerformanceWish).player_name,actor_id:target.actor_id,role_id:target.role_id,note:(target as PerformanceWish).note||"",reason:""});preview.value=null;if(auth.token){[actors.value,roles.value]=await Promise.all([adminApi.getActors(auth.token),adminApi.getRoles(auth.token,props.theaterId)]);}}, {immediate:true});
watch(()=>[form.player_name,form.actor_id,form.role_id,form.note,form.reason],()=>preview.value=null);
const payload=()=>({player_name:form.player_name.trim(),actor_id:form.actor_id,role_id:form.role_id,note:form.note.trim()||null,reason:form.reason.trim()});
const immutable=(field:string)=>preview.value?.immutable_fields.includes(field)??false;
const previewText=computed(()=>preview.value?.requires_reversal?"将撤销原权益核销并退回原道具，修订后重新进入核对。":"将建立新版本，原始登记和修订原因会永久保留。");
async function loadPreview(){if(!auth.token||!props.target)return;busy.value=true;try{preview.value=props.kind==="designation"?await adminApi.previewDesignationCorrection(auth.token,props.target as Predesignation,payload()):await adminApi.previewWishCorrection(auth.token,props.target as PerformanceWish,payload());}catch(e:any){ElMessage.error(e.message||"修订预览失败")}finally{busy.value=false}}
async function submit(){if(!auth.token||!props.target||!preview.value)return;try{await confirmAction({title:"确认修订登记",message:`修订原因：${form.reason.trim()}\n系统会保留原版本，此操作可追溯。`,tone:"warning",confirmButtonText:"确认建立新版本"})}catch{return}busy.value=true;try{if(props.kind==="designation")await adminApi.correctDesignation(auth.token,props.target as Predesignation,payload());else await adminApi.correctWish(auth.token,props.target as PerformanceWish,payload());ElMessage.success("登记信息已修订");emit("changed");close()}catch(e:any){ElMessage.error(e.message||"修订失败")}finally{busy.value=false}}
function close(){emit("update:modelValue",false)}
</script>

<style scoped>
.correction-body{display:grid;gap:16px}.form-grid{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px}label{display:grid;gap:7px;color:#596579;font-size:14px}.required{color:#ef4444;font-size:12px}.preview-box{display:grid;gap:5px;padding:14px;border:1px solid #dce8ff;border-radius:12px;background:#f5f8ff;color:#52627b}.preview-box strong{color:#172033}.preview-box small{color:#d97706}@media(max-width:620px){.form-grid{grid-template-columns:1fr}}
</style>
