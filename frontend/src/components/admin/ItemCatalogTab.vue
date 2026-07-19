<template>
  <div class="catalog-workspace">
    <div class="toolbar">
      <div><h2>道具配置</h2><p>配置当前剧场可发放的指定类与通用类道具。</p></div>
      <div class="toolbar-actions"><el-button @click="createDefaults">创建默认指定道具</el-button><el-button type="primary" @click="openCreate">新增道具</el-button></div>
    </div>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!definitions.length" description="当前剧场尚未配置道具">
      <el-button type="primary" @click="createDefaults">创建万能、榜三和对位指定</el-button>
    </el-empty>
    <div v-else class="catalog-groups">
      <section v-for="group in groups" :key="group.category" class="catalog-group">
        <div class="group-title"><strong>{{ group.label }}</strong><span>{{ group.items.length }} 种</span></div>
        <div class="definition-grid">
          <article v-for="item in group.items" :key="item.id" class="definition-card" :class="{ inactive: !item.is_active }" :style="{ '--item-color': item.color }">
            <div class="definition-main"><span class="color-dot"/><div><strong>{{ item.display_name }}</strong><small>{{ item.code }}</small></div></div>
            <div class="definition-meta"><el-tag size="small" effect="plain">{{ item.category === 'designation' ? bindingLabel(item.designation_type) : '通用道具' }}</el-tag><span>默认 {{ item.default_validity_days }} 天</span><span v-if="item.category === 'designation'">优先级 {{ item.priority }}</span></div>
            <p>{{ item.description || "暂无说明" }}</p>
            <div class="definition-actions"><el-tag :type="item.is_active ? 'success' : 'info'">{{ item.is_active ? '启用中' : '已停用' }}</el-tag><el-button link type="primary" @click="openEdit(item)">编辑</el-button><el-button link :type="item.is_active ? 'danger' : 'success'" @click="toggle(item)">{{ item.is_active ? '停用' : '启用' }}</el-button></div>
          </article>
        </div>
      </section>
    </div>
    <el-drawer v-model="drawer" :title="editing ? '编辑道具' : '新增道具'" size="460px">
      <el-form label-position="top">
        <el-form-item label="道具名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="唯一编码"><el-input v-model="form.code" :disabled="!!editing" placeholder="如 drink_ticket" /></el-form-item>
        <div class="two"><el-form-item label="道具类别"><el-select v-model="form.category"><el-option label="指定类" value="designation"/><el-option label="通用类" value="general"/></el-select></el-form-item><el-form-item v-if="form.category === 'designation'" label="指定规则"><el-select v-model="form.designation_type"><el-option label="万能指定" value="universal"/><el-option label="榜三指定" value="top_three"/><el-option label="对位指定" value="paired"/></el-select></el-form-item></div>
        <div class="two"><el-form-item label="默认有效期（天）"><el-input-number v-model="form.default_validity_days" :min="1" :max="3650" /></el-form-item><el-form-item label="显示颜色"><el-color-picker v-model="form.color" /></el-form-item></div>
        <div class="two"><el-form-item label="优先级"><el-input-number v-model="form.priority" :min="0" :disabled="form.category !== 'designation'" /></el-form-item><el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item></div>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="drawer=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-drawer>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { DesignationBinding, EntitlementItemType, ItemCategory } from "../../features/entitlements/types";
const props = defineProps<{ theaterId: number; definitions: EntitlementItemType[]; loading?: boolean }>();
const emit = defineEmits<{ refresh: [] }>();
const auth=useAuthStore(), drawer=ref(false), saving=ref(false), editing=ref<EntitlementItemType|null>(null);
const blank=()=>({ code:"",display_name:"",category:"general" as ItemCategory,designation_type:null as DesignationBinding|null,priority:0,default_validity_days:90,color:"#409eff",icon:null as string|null,description:"",is_active:true,sort_order:0 });
const form=reactive(blank());
const groups=computed(()=>[{category:"designation",label:"指定类道具",items:props.definitions.filter(i=>i.category==="designation")},{category:"general",label:"通用道具",items:props.definitions.filter(i=>i.category==="general")}].filter(g=>g.items.length));
const bindingLabel=(value: DesignationBinding|null)=>({universal:"万能指定",top_three:"榜三指定",paired:"对位指定"}[value||"universal"]);
function openCreate(){ editing.value=null; Object.assign(form,blank()); drawer.value=true; }
function openEdit(item:EntitlementItemType){ editing.value=item; Object.assign(form,item); drawer.value=true; }
async function save(){ if(!auth.token||!form.display_name.trim()||!form.code.trim()) return ElMessage.warning("请完整填写名称和编码"); saving.value=true; try { const payload={...form,designation_type:form.category==="designation"?form.designation_type:null,description:form.description||null}; if(editing.value) await adminApi.updateEntitlementItemType(auth.token,editing.value.id,payload); else await adminApi.createEntitlementItemType(auth.token,props.theaterId,payload); ElMessage.success("道具配置已保存"); drawer.value=false; emit("refresh"); } catch(e:any){ElMessage.error(e.message)} finally{saving.value=false;} }
async function toggle(item:EntitlementItemType){ if(!auth.token)return; await ElMessageBox.confirm(`确认${item.is_active?'停用':'启用'}“${item.display_name}”？`,"操作确认",{type:"warning"}); try{await adminApi.updateEntitlementItemType(auth.token,item.id,{is_active:!item.is_active});ElMessage.success("状态已更新");emit("refresh");}catch(e:any){ElMessage.error(e.message)} }
async function createDefaults(){if(!auth.token)return; await ElMessageBox.confirm("将创建万能指定、榜三指定和对位指定三种默认道具。","创建默认指定道具",{type:"info",confirmButtonText:"确认创建",cancelButtonText:"取消"});try{await adminApi.createDefaultDesignationTypes(auth.token,props.theaterId);ElMessage.success("默认指定道具已创建");emit("refresh");}catch(e:any){ElMessage.error(e.message)}}
</script>
<style scoped>
.catalog-workspace{display:grid;gap:20px}.toolbar,.definition-actions,.definition-main,.group-title{display:flex;align-items:center;justify-content:space-between;gap:14px}.toolbar{padding:22px 24px;background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px}.toolbar h2{margin:0 0 6px}.toolbar p,.definition-card p{margin:0;color:var(--el-text-color-secondary)}.toolbar-actions{display:flex;gap:10px}.catalog-groups{display:grid;gap:20px}.catalog-group{background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px;padding:22px}.group-title{margin-bottom:16px}.group-title span{color:var(--el-text-color-secondary)}.definition-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}.definition-card{border:1px solid var(--el-border-color-lighter);border-left:4px solid var(--item-color);border-radius:12px;padding:18px;display:grid;gap:14px}.definition-card.inactive{opacity:.62}.definition-main{justify-content:flex-start}.definition-main div{display:grid}.definition-main small{color:var(--el-text-color-secondary);margin-top:4px}.color-dot{width:12px;height:12px;border-radius:50%;background:var(--item-color)}.definition-meta{display:flex;gap:12px;align-items:center;color:var(--el-text-color-secondary);font-size:13px}.definition-actions{justify-content:flex-end}.definition-actions .el-tag{margin-right:auto}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.el-select{width:100%}@media(max-width:700px){.toolbar{align-items:flex-start;flex-direction:column}.definition-grid,.two{grid-template-columns:1fr}}
</style>
