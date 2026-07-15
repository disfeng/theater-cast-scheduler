<template>
  <section class="settings-page">
    <PageHeader title="基础配置" description="按剧场管理演出场次、周模板和角色；同名角色可在不同剧场独立配置。" />

    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
    <el-alert v-if="success" :title="success" type="success" show-icon closable @close="success = ''" />

    <el-card shadow="never" class="overview-card">
      <div class="overview">
        <div class="theater-picker">
          <span class="section-label">当前剧场</span>
          <el-select v-model="selectedTheaterId" placeholder="请选择剧场" @change="loadTheaterDetails">
            <el-option v-for="item in theaters" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-tag v-if="selectedTheater" type="success" effect="light">启用中</el-tag>
        </div>
        <div v-if="selectedTheater" class="overview-stats">
          <div><strong>{{ activeSlots.length }}</strong><span>场次</span></div>
          <div><strong>{{ activeRoles.length }}</strong><span>角色</span></div>
        </div>
        <div class="overview-actions">
          <el-dropdown v-if="selectedTheater" trigger="click" @command="handleTheaterCommand">
            <el-button>剧场操作<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑剧场</el-dropdown-item>
                <el-dropdown-item command="delete" divided class="danger-item">删除剧场</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="primary" @click="openTheaterDialog()">新增剧场</el-button>
        </div>
      </div>
    </el-card>

    <el-empty v-if="!selectedTheater" description="请先新增或选择剧场" />
    <el-card v-else shadow="never" class="configuration-card">
      <el-tabs v-model="activeSettingsTab" class="configuration-tabs">
        <el-tab-pane label="场次配置" name="slots">
          <div class="panel-heading">
            <div><strong>场次配置</strong><span>维护每天可用的演出时间</span></div>
            <el-button type="primary" @click="openSlotDialog()">新增场次</el-button>
          </div>
          <el-table :data="slots" empty-text="暂无场次" class="compact-table">
            <el-table-column prop="name" label="场次名称" />
            <el-table-column prop="start_time" label="开始时间" width="140"><template #default="{ row }">{{ row.start_time.slice(0, 5) }}</template></el-table-column>
            <el-table-column prop="sort_order" label="排序" width="90" />
            <el-table-column label="操作" width="150" align="right">
              <template #default="{ row }"><el-button size="small" @click="openSlotDialog(row)">编辑</el-button><el-button size="small" type="danger" plain @click="removeSlot(row)">删除</el-button></template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="默认周模板" name="template">
          <div class="panel-heading">
            <div><strong>默认周模板</strong><span>设置每周各天默认开启的场次</span></div>
            <el-button type="primary" @click="saveTemplate">保存周模板</el-button>
          </div>
          <div class="template-grid">
            <section v-for="day in DAYS" :key="day.key" class="template-day-card">
              <strong>{{ day.label }}</strong>
              <el-checkbox-group v-model="weeklyTemplate[day.key]" class="day-slots">
                <el-checkbox v-for="slot in activeSlots" :key="slot.id" :value="slot.id" border>
                  <span>{{ slot.name }}</span><small>{{ slot.start_time.slice(0, 5) }}</small>
                </el-checkbox>
              </el-checkbox-group>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="剧场角色" name="roles">
          <div class="panel-heading role-heading">
            <div><strong>剧场角色</strong><span>角色归属于 {{ selectedTheater.name }}</span></div>
            <div class="role-tools"><el-input v-model="roleSearch" clearable placeholder="搜索角色或分组" aria-label="搜索角色或分组" /><el-button type="primary" @click="openRoleDialog()">新增角色</el-button></div>
          </div>
          <el-table :data="filteredRoles" empty-text="暂无匹配角色" class="compact-table">
            <el-table-column prop="name" label="角色名称" />
            <el-table-column prop="group_name" label="分组"><template #default="{ row }"><el-tag :type="row.group_name ? 'primary' : 'info'" effect="plain">{{ row.group_name || '未分组' }}</el-tag></template></el-table-column>
            <el-table-column label="出演演员" min-width="220">
              <template #default="{ row }"><span :class="{ 'role-actors-empty': actorNamesForRole(row.id) === '暂无演员' }">{{ actorNamesForRole(row.id) }}</span></template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="right"><template #default="{ row }"><el-button size="small" @click="openRoleDialog(row)">编辑</el-button><el-button size="small" type="danger" plain @click="removeRole(row)">删除</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="theaterDialog" :title="editingTheaterId ? '编辑剧场' : '新增剧场'" width="420px">
      <el-form label-position="top"><el-form-item label="剧场名称"><el-input v-model="theaterName" placeholder="例如：西安幽州剧场" /></el-form-item></el-form>
      <template #footer><el-button @click="theaterDialog = false">取消</el-button><el-button type="primary" @click="saveTheater">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="slotDialog" :title="editingSlotId ? '编辑场次' : '新增场次'" width="460px">
      <el-form label-position="top">
        <el-form-item label="场次名称"><el-input v-model="slotForm.name" placeholder="例如：早场、午场、晚场" /></el-form-item>
        <el-form-item label="开始时间"><el-time-picker v-model="slotForm.start_time" value-format="HH:mm:ss" format="HH:mm" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="slotForm.sort_order" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="slotDialog = false">取消</el-button><el-button type="primary" @click="saveSlot">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="roleDialog" :title="editingRoleId ? '编辑角色' : '新增角色'" width="460px">
      <el-form label-position="top">
        <el-form-item label="所属剧场"><el-input :model-value="selectedTheater?.name" disabled /></el-form-item>
        <el-form-item label="角色名称"><el-input v-model="roleForm.name" /></el-form-item>
        <el-form-item label="角色分组"><el-input v-model="roleForm.group_name" placeholder="例如：女位 / 男位 / 辅助" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="roleDialog = false">取消</el-button><el-button type="primary" @click="saveRole">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";
import { adminApi, type Actor, type Role, type Theater, type TheaterSlot, type WeeklyTemplate } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import PageHeader from "../../components/PageHeader.vue";

const DAYS = [{ key: "monday", label: "周一" }, { key: "tuesday", label: "周二" }, { key: "wednesday", label: "周三" }, { key: "thursday", label: "周四" }, { key: "friday", label: "周五" }, { key: "saturday", label: "周六" }, { key: "sunday", label: "周日" }];
const emptyTemplate = (): WeeklyTemplate => Object.fromEntries(DAYS.map((day) => [day.key, []]));
const auth = useAuthStore();
const theaters = ref<Theater[]>([]), slots = ref<TheaterSlot[]>([]), roles = ref<Role[]>([]), actors = ref<Actor[]>([]);
const selectedTheaterId = ref<number>(), weeklyTemplate = ref<WeeklyTemplate>(emptyTemplate());
const selectedTheater = computed(() => theaters.value.find((item) => item.id === selectedTheaterId.value));
const activeSlots = computed(() => slots.value.filter((item) => item.is_active));
const activeRoles = computed(() => roles.value.filter((item) => item.is_active));
const activeSettingsTab = ref("slots"), roleSearch = ref("");
const filteredRoles = computed(() => {
  const query = roleSearch.value.trim().toLocaleLowerCase();
  if (!query) return roles.value;
  return roles.value.filter((item) => `${item.name} ${item.group_name || ""}`.toLocaleLowerCase().includes(query));
});
const actorNamesForRole = (roleId: number) => {
  const names = actors.value.filter((actor) => actor.role_ids.includes(roleId)).map((actor) => actor.display_name);
  return names.length ? names.join("、") : "暂无演员";
};
const error = ref(""), success = ref("");
const theaterDialog = ref(false), slotDialog = ref(false), roleDialog = ref(false);
const editingTheaterId = ref<number>(), editingSlotId = ref<number>(), editingRoleId = ref<number>();
const theaterName = ref("");
const slotForm = reactive({ name: "", start_time: "14:00:00", sort_order: 0 });
const roleForm = reactive({ name: "", group_name: "" });
const token = () => auth.token as string;
const report = (err: any) => { error.value = err?.message || "操作失败"; };

async function refreshTheaters() {
  [theaters.value, actors.value] = await Promise.all([adminApi.getTheaters(token()), adminApi.getActors(token())]);
  if (!selectedTheaterId.value && theaters.value.length) selectedTheaterId.value = theaters.value[0].id;
  await loadTheaterDetails();
}
async function loadTheaterDetails() {
  if (!selectedTheaterId.value) return;
  [slots.value, roles.value, weeklyTemplate.value] = await Promise.all([
    adminApi.getTheaterSlots(token(), selectedTheaterId.value),
    adminApi.getRoles(token(), selectedTheaterId.value),
    adminApi.getWeeklyTemplate(token(), selectedTheaterId.value),
  ]);
  weeklyTemplate.value = { ...emptyTemplate(), ...weeklyTemplate.value };
}
function openTheaterDialog(item?: Theater) { editingTheaterId.value = item?.id; theaterName.value = item?.name || ""; theaterDialog.value = true; }
function handleTheaterCommand(command: string) { if (command === "edit" && selectedTheater.value) openTheaterDialog(selectedTheater.value); if (command === "delete") removeTheater(); }
async function saveTheater() { try { const item = editingTheaterId.value ? await adminApi.updateTheater(token(), editingTheaterId.value, { name: theaterName.value }) : await adminApi.createTheater(token(), { name: theaterName.value }); selectedTheaterId.value = item.id; theaterDialog.value = false; success.value = "剧场已保存"; await refreshTheaters(); } catch (err) { report(err); } }
async function removeTheater() { if (!selectedTheaterId.value) return; try { await ElMessageBox.confirm("仅未被业务数据引用的剧场可直接删除。", "删除剧场", { type: "warning" }); await adminApi.deleteTheater(token(), selectedTheaterId.value); selectedTheaterId.value = undefined; await refreshTheaters(); } catch (err: any) { if (err !== "cancel") report(err); } }
function openSlotDialog(item?: TheaterSlot) { editingSlotId.value = item?.id; Object.assign(slotForm, item ? { name: item.name, start_time: item.start_time, sort_order: item.sort_order } : { name: "", start_time: "14:00:00", sort_order: slots.value.length }); slotDialog.value = true; }
async function saveSlot() { if (!selectedTheaterId.value) return; try { const payload = { ...slotForm }; if (editingSlotId.value) await adminApi.updateTheaterSlot(token(), editingSlotId.value, payload); else await adminApi.createTheaterSlot(token(), selectedTheaterId.value, payload); slotDialog.value = false; success.value = "场次已保存"; await loadTheaterDetails(); } catch (err) { report(err); } }
async function removeSlot(item: TheaterSlot) { try { await ElMessageBox.confirm(`确定删除场次“${item.name}”？`, "删除场次", { type: "warning" }); await adminApi.deleteTheaterSlot(token(), item.id); await loadTheaterDetails(); } catch (err: any) { if (err !== "cancel") report(err); } }
async function saveTemplate() { if (!selectedTheaterId.value) return; try { await adminApi.updateWeeklyTemplate(token(), selectedTheaterId.value, weeklyTemplate.value); success.value = "周模板已保存"; } catch (err) { report(err); } }
function openRoleDialog(item?: Role) { editingRoleId.value = item?.id; Object.assign(roleForm, { name: item?.name || "", group_name: item?.group_name || "" }); roleDialog.value = true; }
async function saveRole() { if (!selectedTheaterId.value) return; try { const payload = { name: roleForm.name, group_name: roleForm.group_name || null }; if (editingRoleId.value) await adminApi.updateRole(token(), editingRoleId.value, payload); else await adminApi.createRole(token(), { theater_id: selectedTheaterId.value, ...payload }); roleDialog.value = false; success.value = "角色已保存"; await loadTheaterDetails(); } catch (err) { report(err); } }
async function removeRole(item: Role) { try { await ElMessageBox.confirm(`确定删除角色“${item.name}”？`, "删除角色", { type: "warning" }); await adminApi.deleteRole(token(), item.id); await loadTheaterDetails(); } catch (err: any) { if (err !== "cancel") report(err); } }
onMounted(() => refreshTheaters().catch(report));
</script>

<style scoped>
.settings-page { width: 100%; display: grid; gap: 16px; }
.overview-card :deep(.el-card__body) { padding: 16px 20px; }
.overview { display: flex; align-items: center; gap: 24px; min-height: 40px; }
.theater-picker { display: flex; align-items: center; gap: 10px; }
.theater-picker :deep(.el-select) { width: 260px; }
.section-label { color: var(--text-secondary); font-size: 13px; white-space: nowrap; }
.overview-stats { display: flex; gap: 8px; }
.overview-stats div { display: flex; align-items: baseline; gap: 5px; min-width: 78px; padding: 7px 12px; border-radius: 8px; background: #f6f8fb; }
.overview-stats strong { color: var(--text-primary); font-size: 18px; }
.overview-stats span { color: var(--text-secondary); font-size: 12px; }
.overview-actions { margin-left: auto; display: flex; gap: 8px; }
.configuration-card :deep(.el-card__body) { padding: 0 24px 24px; }
.configuration-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.configuration-tabs :deep(.el-tabs__item) { height: 58px; padding: 0 24px; font-weight: 600; }
.configuration-tabs :deep(.el-tabs__content) { padding-top: 18px; }
.panel-heading { min-height: 44px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.panel-heading > div:first-child { display: flex; align-items: baseline; gap: 10px; }
.panel-heading strong { font-size: 17px; }
.panel-heading span { color: var(--text-secondary); font-size: 13px; }
.compact-table { border: 1px solid #e7ebf1; border-radius: 10px; overflow: hidden; }
.compact-table :deep(th.el-table__cell) { background: #f7f9fc; color: #667085; }
.template-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px; }
.template-day-card { min-width: 0; padding: 13px; border: 1px solid #e3e8f0; border-radius: 10px; background: #fafbfc; }
.template-day-card > strong { display: block; margin-bottom: 11px; font-size: 14px; }
.day-slots { display: grid; gap: 7px; }
.day-slots :deep(.el-checkbox) { width: 100%; height: auto; min-height: 36px; margin: 0; padding: 7px 9px; display: flex; }
.day-slots :deep(.el-checkbox__label) { min-width: 0; padding-left: 7px; display: flex; justify-content: space-between; flex: 1; gap: 4px; font-size: 12px; }
.day-slots small { color: #98a2b3; font-size: 11px; }
.role-heading { align-items: center; }
.role-tools { display: flex; align-items: center; gap: 8px; }
.role-tools :deep(.el-input) { width: 220px; }
.role-actors-empty { color: var(--text-secondary); }
:global(.danger-item) { color: #f56c6c !important; }
@media (max-width: 1100px) { .template-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 800px) { .overview { flex-wrap: wrap; }.overview-actions { margin-left: 0; }.role-heading, .panel-heading { align-items: flex-start; flex-direction: column; }.role-tools { width: 100%; }.role-tools :deep(.el-input) { width: 100%; } }
@media (max-width: 700px) { .template-grid { grid-template-columns: 1fr; }.theater-picker { flex-wrap: wrap; }.theater-picker :deep(.el-select) { width: 100%; }.overview-stats { width: 100%; } }
</style>
