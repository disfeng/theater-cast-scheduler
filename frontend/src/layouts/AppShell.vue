<template>
  <el-container class="app-shell">
    <el-aside :width="asideWidth" class="sidebar" :class="{ 'is-open': mobileOpen, 'is-collapsed': collapsed && !isMobile }">
      <div class="brand">
        <span class="brand-mark">剧</span>
        <strong v-show="!collapsed">剧场卡司排班</strong>
      </div>

      <el-menu
        :default-active="activePath"
        :collapse="collapsed && !isMobile"
        router
        background-color="transparent"
        text-color="#aeb9cc"
        active-text-color="#ffffff"
        class="sidebar-menu"
        @select="mobileOpen = false"
      >
        <template v-if="authStore.isAdmin">
          <li class="menu-group-title">概览</li>
          <el-menu-item index="/admin/dashboard"><el-icon><DataBoard /></el-icon><template #title>工作台</template></el-menu-item>
          <li class="menu-group-title">剧场运营</li>
          <el-menu-item index="/admin/settings"><el-icon><Setting /></el-icon><template #title>基础配置</template></el-menu-item>
          <el-menu-item index="/admin/actors"><el-icon><User /></el-icon><template #title>演员管理</template></el-menu-item>
          <el-menu-item index="/admin/monthly-plan"><el-icon><Calendar /></el-icon><template #title>月度计划</template></el-menu-item>
          <el-menu-item index="/admin/weekly-scheduling"><el-icon><Grid /></el-icon><template #title>周排班</template></el-menu-item>
          <el-menu-item index="/admin/leave-requests"><el-icon><DocumentChecked /></el-icon><template #title>请假审批</template></el-menu-item>
          <li class="menu-group-title">玩家与权益</li>
          <el-menu-item index="/admin/designations-wishes"><el-icon><MagicStick /></el-icon><template #title>指定与许愿</template></el-menu-item>
          <el-menu-item index="/admin/entitlements"><el-icon><Ticket /></el-icon><template #title>权益管理</template></el-menu-item>
          <li class="menu-group-title">系统治理</li>
          <el-menu-item v-if="authStore.isSuperAdmin" index="/admin/administrators"><el-icon><UserFilled /></el-icon><template #title>管理员管理</template></el-menu-item>
          <el-menu-item index="/admin/audit-logs"><el-icon><Document /></el-icon><template #title>日志审查</template></el-menu-item>
        </template>
        <template v-else>
          <el-menu-item index="/actor/schedule"><el-icon><Clock /></el-icon><template #title>我的排期</template></el-menu-item>
          <el-menu-item index="/actor/leave"><el-icon><Memo /></el-icon><template #title>我的请假</template></el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <div v-if="isMobile && mobileOpen" class="sidebar-mask" @click="mobileOpen = false" />

    <el-container class="workspace">
      <el-header class="topbar">
        <el-button text class="menu-toggle" aria-label="切换导航" @click="toggleSidebar">☰</el-button>
        <div class="topbar-actions">
          <span class="role-label">{{ authStore.isSuperAdmin ? '超级管理员' : authStore.isAdmin ? '剧场管理员' : '演员' }}</span>
          <el-button size="small" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="workspace-main"><RouterView /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Calendar, Clock, DataBoard, Document, DocumentChecked, Grid, MagicStick, Memo, Setting, Ticket, User, UserFilled } from "@element-plus/icons-vue";
import { useAuthStore } from "../auth/store";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const collapsed = ref(false);
const mobileOpen = ref(false);
const isMobile = ref(false);
const activePath = computed(() => route.path);
const asideWidth = computed(() => isMobile.value ? "0" : collapsed.value ? "76px" : "240px");

function syncViewport() {
  isMobile.value = window.innerWidth <= 900;
  if (!isMobile.value) mobileOpen.value = false;
}

function toggleSidebar() {
  if (isMobile.value) mobileOpen.value = !mobileOpen.value;
  else collapsed.value = !collapsed.value;
}

function handleLogout() {
  authStore.logout();
  void router.replace("/login");
}

onMounted(() => { syncViewport(); window.addEventListener("resize", syncViewport); });
onBeforeUnmount(() => window.removeEventListener("resize", syncViewport));
</script>

<style scoped>
.app-shell { min-height: 100vh; }
.sidebar { background: var(--sidebar-bg); transition: width .2s ease; overflow: hidden; z-index: 20; }
.brand { height: 64px; display: flex; align-items: center; gap: 11px; padding: 0 18px; color: #fff; white-space: nowrap; border-bottom: 1px solid rgba(255,255,255,.08); }
.brand-mark { flex: 0 0 36px; height: 36px; display: grid; place-items: center; border-radius: 9px; background: var(--sidebar-active); font-weight: 700; }
.sidebar-menu { border: 0; padding: 14px 10px; }
.menu-group-title { height: 28px; display: flex; align-items: end; padding: 0 12px 5px; margin-top: 9px; color: #6f809c; font-size: 11px; font-weight: 700; letter-spacing: .12em; list-style: none; white-space: nowrap; }
.menu-group-title:first-child { margin-top: 0; }
.sidebar-menu :deep(.el-menu-item) { margin: 4px 0; border-radius: 7px; }
.sidebar-menu :deep(.el-menu-item.is-active) { background: var(--sidebar-active); }
.sidebar.is-collapsed .brand { justify-content: center; padding: 0; }
.sidebar-menu.el-menu--collapse { width: 100%; box-sizing: border-box; }
.sidebar-menu.el-menu--collapse :deep(.el-menu-item) { width: 100%; justify-content: center; padding: 0 !important; }
.sidebar-menu.el-menu--collapse :deep(.el-menu-item .el-icon) { margin: 0; }
.sidebar.is-collapsed .menu-group-title { height: 13px; padding: 0; margin: 6px 12px 2px; border-top: 1px solid rgba(255,255,255,.08); font-size: 0; }
.workspace { min-width: 0; }
.topbar { height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: #fff; border-bottom: 1px solid var(--panel-border); }
.menu-toggle { font-size: 20px; color: var(--text-primary); }
.topbar-actions { display: flex; align-items: center; gap: 14px; }
.role-label { color: var(--text-secondary); font-size: 14px; }
.workspace-main { padding: 28px; background: var(--workspace-bg); overflow-x: hidden; }
.sidebar-mask { display: none; }
@media (max-width: 900px) {
  .sidebar { position: fixed; inset: 0 auto 0 0; width: 240px !important; transform: translateX(-100%); }
  .sidebar.is-open { transform: translateX(0); }
  .sidebar-mask { display: block; position: fixed; inset: 0; z-index: 15; background: rgba(15,23,42,.42); }
  .workspace-main { padding: 18px 14px; }
  .topbar { padding: 0 14px; }
}
</style>
