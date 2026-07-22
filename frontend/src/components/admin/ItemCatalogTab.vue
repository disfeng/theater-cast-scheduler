<template>
  <div class="catalog-workspace">
    <div class="toolbar">
      <div><h2>道具配置</h2><p>配置当前剧场可发放的指定类与通用类道具。</p></div>
      <div class="toolbar-actions"><el-button @click="openDefaultsDialog">创建默认指定道具</el-button><el-button type="primary" @click="openCreate">新增道具</el-button></div>
    </div>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!definitions.length" description="当前剧场尚未配置道具">
      <el-button type="primary" @click="openDefaultsDialog">创建万能、榜三和对位指定</el-button>
    </el-empty>
    <div v-else class="catalog-groups">
      <section v-for="group in groups" :key="group.category" class="catalog-group">
        <div class="group-title"><strong>{{ group.label }}</strong><span>{{ group.items.length }} 种</span></div>
        <div class="definition-grid">
          <article v-for="item in group.items" :key="item.id" class="definition-card" :class="{ inactive: !item.is_active }" :style="{ '--item-color': item.color }">
            <div class="definition-main"><span class="color-dot"/><div><strong>{{ item.display_name }}</strong></div></div>
            <div class="definition-meta"><el-tag size="small" effect="plain">{{ item.category === 'designation' ? bindingLabel(item.designation_type) : '通用道具' }}</el-tag><el-tag size="small" type="info" effect="plain">{{ bindingModeLabel(item) }}</el-tag><span>默认 {{ item.default_validity_days }} 天</span><span v-if="item.category === 'designation'">优先级 {{ item.priority }}</span></div>
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
        <el-form-item label="使用绑定方式"><div class="binding-panel"><div><strong>{{ bindingModeLabel(form) }}</strong><small>{{ bindingHelp }}</small></div><div class="binding-switches"><el-checkbox v-model="form.binds_beneficiary" :disabled="!!editing?.binding_locked_at">限定权益持有人本人使用</el-checkbox><el-checkbox v-model="form.binds_actor" :disabled="!!editing?.binding_locked_at">发放时绑定演员</el-checkbox></div><el-alert v-if="editing?.binding_locked_at" title="该道具已发放，绑定方式已锁定" type="info" :closable="false" show-icon/></div></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="drawer=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-drawer>
    <el-dialog v-model="defaultsDialogOpen" title="创建默认指定道具" width="min(500px, calc(100vw - 32px))" class="app-dialog defaults-dialog" align-center>
      <div class="defaults-dialog-content">
        <p class="defaults-intro">为当前剧场快速建立一套标准指定权益。</p>
        <div class="default-item-previews">
          <div v-for="(item, index) in defaultDesignationItems" :key="item.name" class="default-item-preview">
            <span>{{ index + 1 }}</span>
            <strong>{{ item.name }}</strong>
            <small>{{ item.description }}</small>
          </div>
        </div>
        <p class="defaults-note">已存在的默认道具不会重复创建</p>
      </div>
      <template #footer>
        <el-button :disabled="creatingDefaults" @click="defaultsDialogOpen=false">取消</el-button>
        <el-button type="primary" :loading="creatingDefaults" @click="confirmCreateDefaults">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { adminApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import type { DesignationBinding, EntitlementItemType, ItemCategory } from "../../features/entitlements/types";
import { confirmAction } from "../../features/dialogs/confirm-action";
import { bindingModeLabel } from "../../features/entitlements/format";
const props = defineProps<{ theaterId: number; definitions: EntitlementItemType[]; loading?: boolean }>();
const emit = defineEmits<{ refresh: [] }>();
const auth=useAuthStore(), drawer=ref(false), saving=ref(false), editing=ref<EntitlementItemType|null>(null), defaultsDialogOpen=ref(false), creatingDefaults=ref(false);
const defaultDesignationItems=[{name:"万能指定",description:"指定任意可出演角色"},{name:"榜三指定",description:"热力榜前三权益"},{name:"对位指定",description:"指定对位角色演员"}];
const blank=()=>({ code:"",display_name:"",category:"general" as ItemCategory,designation_type:null as DesignationBinding|null,priority:0,default_validity_days:90,color:"#2f6fed",icon:null as string|null,description:"",is_active:true,sort_order:0,binds_beneficiary:false,binds_actor:false,binding_locked_at:null as string|null });
const form=reactive(blank());
const bindingHelp=computed(()=>form.binds_actor?(form.binds_beneficiary?"只能由持有人本人使用，且只能指定发放时绑定的演员。":"可代指定给其他玩家，但只能指定发放时绑定的演员。"):(form.binds_beneficiary?"只能由权益持有人本人使用，但不限制指定演员。":"可给任意玩家使用，也不限制指定演员。"));
const groups=computed(()=>[{category:"designation",label:"指定类道具",items:props.definitions.filter(i=>i.category==="designation")},{category:"general",label:"通用道具",items:props.definitions.filter(i=>i.category==="general")}].filter(g=>g.items.length));
const bindingLabel=(value: DesignationBinding|null)=>({universal:"万能指定",top_three:"榜三指定",paired:"对位指定"}[value||"universal"]);
function openCreate(){ editing.value=null; Object.assign(form,blank()); drawer.value=true; }
function openEdit(item:EntitlementItemType){ editing.value=item; Object.assign(form,item); drawer.value=true; }
async function save(){ if(!auth.token||!form.display_name.trim()||!form.code.trim()) return ElMessage.warning("请完整填写名称和编码"); saving.value=true; try { const payload={...form,designation_type:form.category==="designation"?form.designation_type:null,description:form.description||null}; if(editing.value) await adminApi.updateEntitlementItemType(auth.token,editing.value.id,payload); else await adminApi.createEntitlementItemType(auth.token,props.theaterId,payload); ElMessage.success("道具配置已保存"); drawer.value=false; emit("refresh"); } catch(e:any){ElMessage.error(e.message)} finally{saving.value=false;} }
async function toggle(item:EntitlementItemType){ if(!auth.token)return; await confirmAction({title:"操作确认",message:`确认${item.is_active?'停用':'启用'}“${item.display_name}”？`,tone:item.is_active?"warning":"primary",confirmButtonText:item.is_active?"确认停用":"确认启用"}); try{await adminApi.updateEntitlementItemType(auth.token,item.id,{is_active:!item.is_active});ElMessage.success("状态已更新");emit("refresh");}catch(e:any){ElMessage.error(e.message)} }
function openDefaultsDialog(){defaultsDialogOpen.value=true;}
async function confirmCreateDefaults(){if(!auth.token)return;creatingDefaults.value=true;try{await adminApi.createDefaultDesignationTypes(auth.token,props.theaterId);defaultsDialogOpen.value=false;ElMessage.success("默认指定道具已创建");emit("refresh");}catch(e:any){ElMessage.error(e.message)}finally{creatingDefaults.value=false;}}
</script>
<style scoped>
.catalog-workspace{display:grid;gap:20px}.toolbar,.definition-actions,.definition-main,.group-title{display:flex;align-items:center;justify-content:space-between;gap:14px}.toolbar{padding:22px 24px;background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px}.toolbar h2{margin:0 0 6px}.toolbar p,.definition-card p{margin:0;color:var(--el-text-color-secondary)}.toolbar-actions{display:flex;gap:10px}.catalog-groups{display:grid;gap:20px}.catalog-group{background:#fff;border:1px solid var(--el-border-color-lighter);border-radius:14px;padding:22px}.group-title{margin-bottom:16px}.group-title span{color:var(--el-text-color-secondary)}.definition-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}.definition-card{border:1px solid var(--el-border-color-lighter);border-left:4px solid var(--item-color);border-radius:12px;padding:18px;display:grid;gap:14px}.definition-card.inactive{opacity:.62}.definition-main{justify-content:flex-start}.definition-main div{display:grid}.definition-main small{color:var(--el-text-color-secondary);margin-top:4px}.color-dot{width:12px;height:12px;border-radius:50%;background:var(--item-color)}.definition-meta{display:flex;gap:12px;align-items:center;color:var(--el-text-color-secondary);font-size:13px}.definition-actions{justify-content:flex-end}.definition-actions .el-tag{margin-right:auto}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.el-select{width:100%}.defaults-dialog-content{display:grid;gap:18px}.defaults-intro,.defaults-note{margin:0;color:var(--el-text-color-secondary)}.default-item-previews{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.default-item-preview{min-width:0;padding:14px 12px;background:#f4f8ff;border:1px solid #dce8ff;border-radius:12px;display:grid;gap:5px}.default-item-preview span{width:24px;height:24px;border-radius:8px;background:#e1ecff;color:var(--el-color-primary);display:grid;place-items:center;font-weight:700;font-size:12px}.default-item-preview strong{color:var(--el-text-color-primary);font-size:14px}.default-item-preview small{color:var(--el-text-color-secondary);line-height:1.45}.defaults-note{padding-top:14px;border-top:1px solid var(--el-border-color-lighter);font-size:13px}.defaults-note::before{content:"✓";display:inline-grid;place-items:center;width:18px;height:18px;margin-right:7px;border-radius:50%;background:#ecf8f2;color:var(--el-color-success);font-weight:700}:deep(.defaults-dialog){border-radius:16px}:deep(.defaults-dialog .el-dialog__header){padding:24px 24px 8px}:deep(.defaults-dialog .el-dialog__title){font-size:20px;font-weight:700;color:var(--el-text-color-primary)}:deep(.defaults-dialog .el-dialog__body){padding:14px 24px 20px}:deep(.defaults-dialog .el-dialog__footer){padding:0 24px 24px}@media(max-width:700px){.toolbar{align-items:flex-start;flex-direction:column}.definition-grid,.two{grid-template-columns:1fr}.default-item-previews{grid-template-columns:1fr}.default-item-preview{grid-template-columns:auto 1fr;align-items:center}.default-item-preview small{grid-column:2}}
.binding-panel{width:100%;display:grid;gap:12px;padding:14px;border:1px solid var(--el-border-color-lighter);border-radius:12px;background:var(--el-fill-color-lighter)}.binding-panel>div:first-child{display:grid;gap:4px}.binding-panel small{color:var(--el-text-color-secondary);line-height:1.5}.binding-switches{display:flex;flex-wrap:wrap;gap:8px 22px}
</style>
