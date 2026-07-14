<template>
  <el-container style="min-height: 100vh;">
    <el-aside width="260px" style="background: var(--sidebar-bg); border-right: 1px solid var(--panel-border);">
      <div style="padding: 24px; text-align: center; border-bottom: 1px solid var(--panel-border);">
        <h3 style="margin: 0; font-weight: 700; color: #fff; letter-spacing: 0.5px;">剧场卡司排班</h3>
      </div>
      
      <el-menu
        :default-active="activePath"
        router
        background-color="transparent"
        text-color="var(--text-secondary)"
        active-text-color="#fff"
        style="border: none; padding: 20px 10px;"
      >
        <template v-if="authStore.role === 'admin'">
          <el-menu-item index="/admin/dashboard">
            <span style="font-weight: 500;">工作台</span>
          </el-menu-item>
          <el-menu-item index="/admin/settings">
            <span style="font-weight: 500;">基础配置</span>
          </el-menu-item>
          <el-menu-item index="/admin/actors">
            <span style="font-weight: 500;">演员管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/monthly-plan">
            <span style="font-weight: 500;">月度计划</span>
          </el-menu-item>
          <el-menu-item index="/admin/designations-wishes">
            <span style="font-weight: 500;">指定与许愿</span>
          </el-menu-item>
          <el-menu-item index="/admin/leave-requests">
            <span style="font-weight: 500;">请假审批</span>
          </el-menu-item>
          <el-menu-item index="/admin/weekly-scheduling">
            <span style="font-weight: 500;">周排班</span>
          </el-menu-item>
        </template>
        
        <template v-if="authStore.role === 'actor'">
          <el-menu-item index="/actor/schedule">
            <span style="font-weight: 500;">我的排期</span>
          </el-menu-item>
          <el-menu-item index="/actor/leave">
            <span style="font-weight: 500;">我的请假</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header style="background: rgba(13, 18, 34, 0.4); border-bottom: 1px solid var(--panel-border); display: flex; align-items: center; justify-content: flex-end; padding: 0 30px; backdrop-filter: blur(8px);">
        <div style="display: flex; align-items: center; gap: 16px;">
          <span style="font-size: 14px; color: var(--text-secondary);">
            {{ authStore.role === 'admin' ? '管理员' : '演员' }}
          </span>
          <el-button type="danger" plain size="small" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      
      <el-main style="padding: 40px; background: rgba(7, 10, 19, 0.2);">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../auth/store";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const activePath = computed(() => route.path);

const handleLogout = () => {
  authStore.logout();
  router.push("/login");
};
</script>
