<template>
  <section class="page-shell">
    <header class="page-header"><div><h1>管理员管理</h1><p>创建剧场管理员，并按剧场授予最小操作范围。</p></div><el-button type="primary" @click="openCreate">新增管理员</el-button></header>
    <el-card shadow="never">
      <el-table :data="accounts" v-loading="loading">
        <el-table-column prop="display_name" label="管理员" min-width="150"><template #default="{row}"><strong>{{ row.display_name }}</strong><div class="subtle">{{ row.email }}</div></template></el-table-column>
        <el-table-column label="角色" width="130"><template #default="{row}"><el-tag :type="row.role === 'super_admin' ? 'danger' : 'primary'">{{ row.role === 'super_admin' ? '超级管理员' : '剧场管理员' }}</el-tag></template></el-table-column>
        <el-table-column label="授权剧场" min-width="220"><template #default="{row}">{{ row.role === 'super_admin' ? '全部剧场' : theaterNames(row.theater_ids) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="230" align="right"><template #default="{row}"><el-button link type="primary" @click="openEdit(row)">编辑授权</el-button><el-button link @click="resetPassword(row)">重置密码</el-button></template></el-table-column>
      </el-table>
    </el-card>
    <el-dialog v-model="dialogVisible" width="620" class="app-dialog" :title="editing ? '编辑管理员' : '新增管理员'">
      <el-form label-position="top" class="form-grid">
        <el-form-item label="显示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item v-if="!editing" label="登录账号"><el-input v-model="form.email" /></el-form-item>
        <el-form-item v-if="!editing" label="初始密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item v-if="!editing" label="管理员类型"><el-select v-model="form.role"><el-option label="剧场管理员" value="theater_admin"/><el-option label="超级管理员" value="super_admin"/></el-select></el-form-item>
        <el-form-item v-if="form.role === 'theater_admin'" label="授权剧场" class="span-2"><el-select v-model="form.theater_ids" multiple filterable><el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item>
        <el-form-item v-if="editing" label="账号状态"><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { apiClient } from "../../api/client"; import { adminApi } from "../../api/admin"; import { useAuthStore } from "../../auth/store";
type Account={id:number;email:string;display_name:string;role:"super_admin"|"theater_admin";is_active:boolean;theater_ids:number[];last_login_at:string|null};
const auth=useAuthStore(), accounts=ref<Account[]>([]), theaters=ref<{id:number;name:string}[]>([]), loading=ref(false), saving=ref(false), dialogVisible=ref(false), editing=ref<Account|null>(null);
const form=reactive({email:"",display_name:"",password:"",role:"theater_admin" as "super_admin"|"theater_admin",theater_ids:[] as number[],is_active:true});
const theaterNames=(ids:number[])=>ids.map(id=>theaters.value.find(t=>t.id===id)?.name||`#${id}`).join("、")||"未授权";
async function load(){loading.value=true;try{[accounts.value,theaters.value]=await Promise.all([apiClient.request<Account[]>("/admin/administrator-accounts",{token:auth.token}),adminApi.getTheaters(auth.token!)]);}finally{loading.value=false}}
function openCreate(){editing.value=null;Object.assign(form,{email:"",display_name:"",password:"",role:"theater_admin",theater_ids:[],is_active:true});dialogVisible.value=true}
function openEdit(row:Account){editing.value=row;Object.assign(form,{email:row.email,display_name:row.display_name,password:"",role:row.role,theater_ids:[...row.theater_ids],is_active:row.is_active});dialogVisible.value=true}
async function save(){saving.value=true;try{if(editing.value)await apiClient.request(`/admin/administrator-accounts/${editing.value.id}`,{method:"PATCH",token:auth.token,body:{display_name:form.display_name,is_active:form.is_active,theater_ids:form.theater_ids}});else await apiClient.request("/admin/administrator-accounts",{method:"POST",token:auth.token,body:form});ElMessage.success("管理员设置已保存");dialogVisible.value=false;await load()}catch(e:any){ElMessage.error(e.message)}finally{saving.value=false}}
async function resetPassword(row:Account){try{const {value}=await ElMessageBox.prompt(`为 ${row.display_name} 设置新密码`,`重置管理员密码`,{inputType:"password",inputValidator:v=>v.length>=8||"密码至少 8 位",customClass:"app-message-box"});await apiClient.request(`/admin/administrator-accounts/${row.id}/reset-password`,{method:"POST",token:auth.token,body:{password:value}});ElMessage.success("密码已重置")}catch{}}
onMounted(load);
</script>
<style scoped>.page-shell{display:grid;gap:20px}.page-header{display:flex;justify-content:space-between;align-items:flex-end}.page-header h1{margin:0;font-size:30px}.page-header p,.subtle{color:var(--text-secondary)}.page-header p{margin:8px 0 0}.subtle{font-size:13px;margin-top:4px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}.span-2{grid-column:1/-1}.form-grid :deep(.el-select){width:100%}</style>
