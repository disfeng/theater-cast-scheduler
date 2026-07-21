<template>
  <div class="login-page">
    <div class="login-brand">
      <span class="login-mark">剧</span>
      <div><strong>剧场卡司排班</strong><small>THEATER CAST SCHEDULER</small></div>
    </div>
    <el-card class="login-card" shadow="never">
      <h1>欢迎登录</h1>
      <p>管理演出计划、演员能力与每周卡司安排</p>
      <el-form label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="邮箱或手机号">
          <el-input v-model="identifier" aria-label="邮箱或手机号" type="text" autocomplete="username" inputmode="text" placeholder="管理员输入邮箱，演员输入手机号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" aria-label="密码" type="password" autocomplete="current-password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
        <el-button type="primary" native-type="submit" class="login-button">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../auth/store";
import { apiClient } from "../api/client";

const identifier = ref("");
const password = ref("");
const error = ref<string | null>(null);

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const handleLogin = async () => {
  error.value = null;
  try {
    const res = await apiClient.login(identifier.value, password.value);
    authStore.setSession(res.access_token, res.role, res.must_change_password);
    const isAdmin = res.role === "admin" || res.role === "super_admin" || res.role === "theater_admin";
    const home = isAdmin ? "/admin/dashboard" : res.must_change_password ? "/actor/change-password" : "/actor/schedule";
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
    const allowedPrefix = isAdmin ? "/admin/" : "/actor/";
    await router.replace(res.must_change_password ? home : redirect.startsWith(allowedPrefix) ? redirect : home);
  } catch (err: any) {
    error.value = err.message || "登录失败";
  }
};
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #eef3f9; }
.login-brand { position: absolute; top: 28px; left: 32px; display: flex; align-items: center; gap: 12px; color: #18233a; }
.login-brand div { display: grid; gap: 2px; }
.login-brand small { color: #7a8699; font-size: 10px; letter-spacing: 1.3px; }
.login-mark { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 9px; color: #fff; background: #2f6fed; font-weight: 700; }
.login-card { width: min(100%, 420px); border-color: var(--panel-border); border-radius: 12px; }
.login-card h1 { margin: 8px 0; font-size: 26px; }
.login-card p { margin: 0 0 26px; color: var(--text-secondary); font-size: 14px; }
.login-button { width: 100%; margin-top: 6px; }
.el-alert { margin-bottom: 18px; }
@media (max-width: 600px) { .login-brand { position: static; margin-bottom: 20px; } .login-page { align-content: center; } }
</style>
