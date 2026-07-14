<template>
  <div class="login-container" style="display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px;">
    <div class="panel" style="max-width: 400px; width: 100%; border-radius: 12px; padding: 40px; box-shadow: var(--panel-shadow);">
      <h2 style="text-align: center; margin-bottom: 30px; font-weight: 700; background: linear-gradient(to right, #6366f1, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">剧场卡司排班系统</h2>
      
      <form @submit.prevent="handleLogin" style="display: grid; gap: 20px;">
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <label for="email" style="font-size: 14px; font-weight: 500; color: var(--text-secondary);">邮箱</label>
          <input
            id="email"
            v-model="email"
            type="email"
            placeholder="请输入邮箱"
            required
            style="width: 100%; padding: 12px; border-radius: 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s;"
          />
        </div>
        
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <label for="password" style="font-size: 14px; font-weight: 500; color: var(--text-secondary);">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            required
            style="width: 100%; padding: 12px; border-radius: 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s;"
          />
        </div>
        
        <button
          type="submit"
          style="width: 100%; padding: 12px; border-radius: 8px; background: var(--primary); color: #fff; border: none; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.2s; margin-top: 10px;"
        >
          登录
        </button>
      </form>

      <div v-if="error" style="margin-top: 16px; color: var(--danger); text-align: center; font-size: 14px;" role="alert">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "../auth/store";
import { apiClient } from "../api/client";

const email = ref("");
const password = ref("");
const error = ref<string | null>(null);

const router = useRouter();
const authStore = useAuthStore();

const handleLogin = async () => {
  error.value = null;
  try {
    const res = await apiClient.login(email.value, password.value);
    authStore.setSession(res.access_token, res.role);
    if (res.role === "admin") {
      router.push("/admin/dashboard");
    } else {
      router.push("/actor/schedule");
    }
  } catch (err: any) {
    error.value = err.message || "登录失败";
  }
};
</script>
