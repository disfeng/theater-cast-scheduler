<template>
  <section class="actors-page">
    <PageHeader title="演员管理" description="管理在册演员的排班偏好、评级和跨剧场角色出演能力。" />
    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />

    <el-card shadow="never" class="actors-card">
      <div class="actors-toolbar">
        <div>
          <strong>演员列表</strong>
          <span>共 {{ filteredActors.length }} 人</span>
        </div>
        <div class="filters">
          <el-input v-model="searchQuery" aria-label="搜索演员" clearable placeholder="搜索演员姓名" />
          <el-select v-model="ratingFilter" aria-label="评级筛选" placeholder="全部评级" clearable>
            <el-option label="高" value="high" /><el-option label="普通" value="normal" /><el-option label="低" value="low" /><el-option label="暂停" value="suspended" />
          </el-select>
          <el-select v-model="theaterFilter" aria-label="剧场筛选" placeholder="全部剧场" clearable>
            <el-option v-for="theater in theaters" :key="theater.id" :label="theater.name" :value="theater.id" />
          </el-select>
          <el-button v-if="hasFilters" @click="resetFilters">清空筛选</el-button>
          <el-button type="primary" @click="openCreate">新增演员</el-button>
        </div>
      </div>

      <el-table :data="filteredActors" empty-text="暂无匹配演员" class="actors-table">
        <el-table-column prop="display_name" label="演员姓名" min-width="120"><template #default="{ row }"><strong>{{ row.display_name }}</strong></template></el-table-column>
        <el-table-column label="评级" width="90"><template #default="{ row }"><el-tag :type="ratingFor(row).type" effect="light">{{ ratingFor(row).label }}</el-tag></template></el-table-column>
        <el-table-column prop="max_consecutive_performances" label="最大连场" width="100" align="center" />
        <el-table-column label="低评级月度上限" width="135" align="center"><template #default="{ row }">{{ row.low_rating_monthly_cap ?? '—' }}</template></el-table-column>
        <el-table-column label="可出演角色" min-width="260">
          <template #default="{ row }">
            <div v-if="roleGroupsForActor(row).length" class="actor-role-groups"><span v-for="line in roleGroupsForActor(row)" :key="line">{{ line }}</span></div>
            <span v-else class="empty-value">暂未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140"><template #default="{ row }"><span :class="{ 'empty-value': !row.notes }">{{ row.notes || '—' }}</span></template></el-table-column>
        <el-table-column label="操作" width="90" align="right"><template #default="{ row }"><el-button size="small" :aria-label="`编辑${row.display_name}`" @click="openEdit(row)">编辑</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <ActorFormDrawer v-model="drawerOpen" :actor="editingActor" :roles="roles" :theaters="theaters" :token="authStore.token || ''" @saved="handleSaved" @error="setError" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { adminApi, type Actor, type Role, type Theater } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
import ActorFormDrawer from "../../components/admin/ActorFormDrawer.vue";
import PageHeader from "../../components/PageHeader.vue";

const authStore = useAuthStore();
const actors = ref<Actor[]>([]), roles = ref<Role[]>([]), theaters = ref<Theater[]>([]);
const searchQuery = ref(""), ratingFilter = ref<Actor["rating_level"] | "">(""), theaterFilter = ref<number | "">("");
const drawerOpen = ref(false), editingActor = ref<Actor | null>(null), error = ref("");
const ratingMeta: Record<Actor["rating_level"], { label: string; type: "success" | "primary" | "warning" | "info" }> = {
  high: { label: "高", type: "success" }, normal: { label: "普通", type: "primary" }, low: { label: "低", type: "warning" }, suspended: { label: "暂停", type: "info" },
};

const hasFilters = computed(() => Boolean(searchQuery.value || ratingFilter.value || theaterFilter.value));
const filteredActors = computed(() => actors.value.filter((actor) => {
  const nameMatches = actor.display_name.toLocaleLowerCase().includes(searchQuery.value.trim().toLocaleLowerCase());
  const ratingMatches = !ratingFilter.value || actor.rating_level === ratingFilter.value;
  const theaterMatches = !theaterFilter.value || roles.value.some((role) => role.theater_id === theaterFilter.value && actor.role_ids.includes(role.id));
  return nameMatches && ratingMatches && theaterMatches;
}));

function roleGroupsForActor(actor: Actor) {
  return theaters.value.flatMap((theater) => {
    const names = roles.value.filter((role) => role.theater_id === theater.id && actor.role_ids.includes(role.id)).map((role) => role.name);
    return names.length ? [`${theater.name}：${names.join("、")}`] : [];
  });
}
function ratingFor(actor: Actor) { return ratingMeta[actor.rating_level]; }

async function refreshData() {
  if (!authStore.token) return;
  try {
    [actors.value, roles.value, theaters.value] = await Promise.all([adminApi.getActors(authStore.token), adminApi.getRoles(authStore.token), adminApi.getTheaters(authStore.token)]);
  } catch (err: any) { error.value = err?.message || "加载演员失败"; }
}
function openCreate() { editingActor.value = null; drawerOpen.value = true; }
function openEdit(actor: Actor) { editingActor.value = actor; drawerOpen.value = true; }
function resetFilters() { searchQuery.value = ""; ratingFilter.value = ""; theaterFilter.value = ""; }
function setError(message: string) { error.value = message; }
async function handleSaved() { error.value = ""; await refreshData(); }
onMounted(refreshData);
</script>

<style scoped>
.actors-page { max-width: 1320px; margin: 0 auto; display: grid; gap: 16px; }
.actors-card :deep(.el-card__body) { padding: 0; }
.actors-toolbar { min-height: 72px; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #e7ebf1; }
.actors-toolbar > div:first-child { display: flex; align-items: baseline; gap: 9px; white-space: nowrap; }
.actors-toolbar strong { font-size: 17px; }.actors-toolbar span { color: var(--text-secondary); font-size: 13px; }
.filters { display: flex; align-items: center; gap: 8px; }.filters :deep(.el-input) { width: 190px; }.filters :deep(.el-select) { width: 150px; }
.actors-table :deep(th.el-table__cell) { background: #f7f9fc; color: #667085; }.actors-table :deep(.el-table__cell) { padding: 11px 0; }
.actor-role-groups { display: grid; gap: 3px; color: #344054; font-size: 13px; line-height: 1.45; }.empty-value { color: #98a2b3; }
@media (max-width: 1000px) { .actors-toolbar { align-items: flex-start; flex-direction: column; }.filters { width: 100%; flex-wrap: wrap; }.filters :deep(.el-input), .filters :deep(.el-select) { width: 180px; } }
</style>
