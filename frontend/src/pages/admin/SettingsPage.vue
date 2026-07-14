<template>
  <section style="max-width: 1200px; margin: 0 auto;">
    <PageHeader title="基础配置" description="在此添加和管理剧场物理场地、默认周模板排班以及可选固定角色。" />

    <div v-if="error" style="padding: 12px; background: #ffeef0; color: #d9383a; border-radius: 6px; margin-bottom: 20px;" role="alert">
      {{ error }}
    </div>

    <div v-if="success" style="padding: 12px; background: #e6f4ea; color: #137333; border-radius: 6px; margin-bottom: 20px;">
      {{ success }}
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px; align-items: start;">
      <!-- Left Column: Input Forms -->
      <div style="display: flex; flex-direction: column; gap: 30px;">
        
        <!-- Theater Configuration Form -->
        <div class="panel" style="margin: 0;">
          <h3>剧场配置</h3>
          <form @submit.prevent="handleSaveTheater" style="display: grid; gap: 16px; margin-top: 10px;">
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="theater-name-input">剧场名称</label>
              <input
                id="theater-name-input"
                v-model="theaterName"
                placeholder="例如：西安幽州剧场"
                required
                style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
              />
            </div>

            <div>
              <label style="display: block; margin-bottom: 8px;">默认周模板配置</label>
              <div style="display: grid; gap: 8px;">
                <div
                  v-for="day in DAYS"
                  :key="day.key"
                  style="display: grid; grid-template-columns: 80px 1fr 1fr; align-items: center; gap: 12px; background: rgba(255, 255, 255, 0.02); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.04);"
                >
                  <span style="font-weight: 600; color: var(--text-secondary); font-size: 14px;">{{ day.label }}</span>
                  
                  <label style="display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; font-size: 13px;">
                    <input
                      type="checkbox"
                      :aria-label="day.label + '下午场'"
                      style="width: 16px; height: 16px; cursor: pointer;"
                      :checked="weeklyTemplate[day.key]?.includes('early') || false"
                      @change="toggleSlot(day.key, 'early')"
                    />
                    下午场
                  </label>
                  
                  <label style="display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; font-size: 13px;">
                    <input
                      type="checkbox"
                      :aria-label="day.label + '晚场'"
                      style="width: 16px; height: 16px; cursor: pointer;"
                      :checked="weeklyTemplate[day.key]?.includes('late') || false"
                      @change="toggleSlot(day.key, 'late')"
                    />
                    晚场
                  </label>
                </div>
              </div>
            </div>

            <button type="submit" style="margin-top: 8px; padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">保存剧场</button>
          </form>
        </div>

        <!-- Role Configuration Form -->
        <div class="panel" style="margin: 0;">
          <h3>新增角色</h3>
          <form @submit.prevent="handleSaveRole" style="display: grid; gap: 16px; margin-top: 10px;">
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="role-name-input">角色名称</label>
              <input
                id="role-name-input"
                v-model="roleName"
                placeholder="例如：长离"
                required
                style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
              />
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label for="role-group-input">角色分组</label>
              <input
                id="role-group-input"
                v-model="groupName"
                placeholder="例如：女位 / 男位 / 辅助"
                style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: var(--text-primary);"
              />
            </div>
            <button type="submit" style="margin-top: 8px; padding: 10px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;">保存角色</button>
          </form>
        </div>

      </div>

      <!-- Right Column: Listings -->
      <div style="display: flex; flex-direction: column; gap: 30px;">
        
        <!-- Configured Theaters List -->
        <div class="panel" style="margin: 0;">
          <h3>已配置剧场 ({{ theaters.length }})</h3>
          <p v-if="theaters.length === 0" style="color: var(--text-secondary); margin-top: 10px;">暂无已配置的剧场。</p>
          <div v-else style="display: grid; gap: 12px; margin-top: 12px;">
            <div
              v-for="theater in theaters"
              :key="theater.id"
              class="panel"
              style="padding: 16px; margin: 0; background: rgba(255, 255, 255, 0.02); border: 1px solid var(--panel-border);"
            >
              <div style="font-weight: 600; font-size: 16px; color: var(--text-primary); margin-bottom: 6px;">
                {{ theater.name }}
              </div>
              <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.5;">
                默认排班：{{ getActiveDaysText(theater) }}
              </div>
            </div>
          </div>
        </div>

        <!-- Configured Roles List -->
        <div class="panel" style="margin: 0;">
          <h3>已配置角色 ({{ roles.length }})</h3>
          <p v-if="roles.length === 0" style="color: var(--text-secondary); margin-top: 10px;">暂无已配置的角色。</p>
          <div v-else style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px;">
            <div
              v-for="role in roles"
              :key="role.id"
              style="padding: 8px 14px; background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 20px; font-size: 13px; color: var(--text-primary); display: inline-flex; align-items: center; gap: 8px;"
            >
              <span style="font-weight: 600;">{{ role.name }}</span>
              <span
                v-if="role.group_name"
                style="font-size: 11px; color: var(--text-secondary); background: rgba(255, 255, 255, 0.05); padding: 2px 6px; border-radius: 10px;"
              >
                {{ role.group_name }}
              </span>
            </div>
          </div>
        </div>

      </div>

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAuthStore } from "../../auth/store";
import { adminApi, Theater, Role } from "../../api/admin";
import PageHeader from "../../components/PageHeader.vue";

const DAYS = [
  { key: "monday", label: "周一" },
  { key: "tuesday", label: "周二" },
  { key: "wednesday", label: "周三" },
  { key: "thursday", label: "周四" },
  { key: "friday", label: "周五" },
  { key: "saturday", label: "周六" },
  { key: "sunday", label: "周日" },
] as const;

const authStore = useAuthStore();

const theaters = ref<Theater[]>([]);
const roles = ref<Role[]>([]);

const theaterName = ref("");
const weeklyTemplate = ref<Record<string, string[]>>({});
const roleName = ref("");
const groupName = ref("");
const error = ref<string | null>(null);
const success = ref<string | null>(null);

const refreshData = () => {
  if (!authStore.token) return;
  adminApi.getTheaters(authStore.token).then((res) => theaters.value = res).catch((err) => error.value = err.message);
  adminApi.getRoles(authStore.token).then((res) => roles.value = res).catch((err) => error.value = err.message);
};

onMounted(() => {
  refreshData();
});

const toggleSlot = (day: string, slot: string) => {
  const current = weeklyTemplate.value[day] || [];
  const updated = current.includes(slot)
    ? current.filter((s) => s !== slot)
    : [...current, slot];
  weeklyTemplate.value = { ...weeklyTemplate.value, [day]: updated };
};

const handleSaveTheater = async () => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.createTheater(authStore.token, {
      name: theaterName.value,
      default_weekly_template: weeklyTemplate.value,
    });
    theaterName.value = "";
    weeklyTemplate.value = {};
    success.value = "剧场保存成功！";
    refreshData();
  } catch (err: any) {
    error.value = err.message || "保存剧场失败";
  }
};

const handleSaveRole = async () => {
  if (!authStore.token) return;
  error.value = null;
  success.value = null;
  try {
    await adminApi.createRole(authStore.token, {
      name: roleName.value,
      group_name: groupName.value || null,
    });
    roleName.value = "";
    groupName.value = "";
    success.value = "角色保存成功！";
    refreshData();
  } catch (err: any) {
    error.value = err.message || "保存角色失败";
  }
};

const getActiveDaysText = (theater: Theater) => {
  const activeDays: string[] = [];
  DAYS.forEach(({ key, label }) => {
    const slots = theater.default_weekly_template?.[key] || [];
    if (slots.length > 0) {
      const slotNames = slots.map((s) => (s === "early" ? "下午" : "晚"));
      activeDays.push(`${label}(${slotNames.join("/")})`);
    }
  });
  return activeDays.length > 0 ? activeDays.join(", ") : "无默认场次";
};
</script>
