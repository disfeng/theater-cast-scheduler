<template>
  <div class="login-page">
    <main class="login-shell">
      <section class="brand-panel" aria-label="系统介绍">
        <div class="stage-grid" aria-hidden="true" />
        <header class="brand-lockup">
          <span class="login-mark">剧</span>
          <div>
            <strong>剧场卡司排班</strong>
            <small>THEATER CAST SCHEDULER</small>
          </div>
        </header>

        <div class="brand-message">
          <span class="section-kicker">CAST OPERATIONS</span>
          <h1>每一场演出，<br />都从清晰的安排开始。</h1>
          <p>将剧场、场次、演员与玩家权益放进同一条可追溯的运营工作流。</p>
          <div class="capability-list">
            <span><el-icon><Calendar /></el-icon>月度场次与周排班</span>
            <span><el-icon><User /></el-icon>演员能力与请假协同</span>
            <span><el-icon><CircleCheck /></el-icon>指定、许愿与权益闭环</span>
          </div>
        </div>

        <footer class="brand-footer">
          <span class="security-dot" />
          <span>运营数据安全访问</span>
          <small>V1 · THEATER WORKSPACE</small>
        </footer>
      </section>

      <section class="form-panel">
        <div class="mobile-brand">
          <span class="login-mark">剧</span>
          <div><strong>剧场卡司排班</strong><small>THEATER CAST SCHEDULER</small></div>
        </div>
        <div class="login-card">
          <div class="form-heading">
            <span class="access-badge"><span />安全访问</span>
            <h2>欢迎回来</h2>
            <p>请使用管理员邮箱或演员手机号登录。</p>
          </div>
          <el-form label-position="top" @submit.prevent="handleLogin">
            <el-form-item label="邮箱或手机号">
              <el-input v-model="identifier" aria-label="邮箱或手机号" type="text" autocomplete="username" inputmode="text" placeholder="输入邮箱或手机号" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" aria-label="密码" type="password" autocomplete="current-password" show-password placeholder="请输入密码" size="large">
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
            <el-button type="primary" native-type="submit" class="login-button" size="large" aria-label="登录">
              <span>登录工作台</span><el-icon><ArrowRight /></el-icon>
            </el-button>
          </el-form>
          <div class="login-help">
            <span><el-icon><CircleCheck /></el-icon>管理员使用邮箱</span>
            <span><el-icon><CircleCheck /></el-icon>演员使用手机号</span>
          </div>
        </div>
        <p class="form-footer">登录即表示你将遵守剧场数据保密规则</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, Calendar, CircleCheck, Lock, User } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../auth/store";
import { ApiError, apiClient } from "../api/client";

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
    const message = loginErrorMessage(err);
    error.value = message;
    ElMessage.error({ message, duration: 4000, showClose: true });
  }
};

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return "账号或密码错误，请检查后重试";
  if (error instanceof TypeError) return "无法连接服务器，请确认服务已启动";
  return error instanceof Error && error.message ? error.message : "登录失败，请稍后重试";
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; padding: 40px; overflow: hidden; background: #e9eff6; color: #172136; }
.login-shell { width: min(1120px, 100%); min-height: 680px; display: grid; grid-template-columns: 1.08fr .92fr; overflow: hidden; border: 1px solid rgba(24, 41, 68, .12); border-radius: 24px; background: #fffdf9; box-shadow: 0 28px 80px rgba(24, 41, 68, .16); }
.brand-panel { position: relative; isolation: isolate; display: flex; flex-direction: column; min-width: 0; padding: 48px 52px 42px; overflow: hidden; background: #13243d; color: #f8fbff; }
.stage-grid { position: absolute; inset: 0; z-index: -1; opacity: .38; background-image: linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.055) 1px, transparent 1px); background-size: 54px 54px; mask-image: linear-gradient(to bottom right, #000, transparent 80%); }
.brand-panel::after { content: ""; position: absolute; right: -150px; bottom: -190px; z-index: -1; width: 460px; height: 460px; border: 1px solid rgba(123, 171, 230, .28); border-radius: 50%; box-shadow: 0 0 0 54px rgba(123, 171, 230, .045), 0 0 0 108px rgba(123, 171, 230, .025); }
.brand-lockup, .mobile-brand { display: flex; align-items: center; gap: 13px; }.brand-lockup > div, .mobile-brand > div { display: grid; gap: 3px; }.brand-lockup strong, .mobile-brand strong { font-size: 17px; letter-spacing: .02em; }.brand-lockup small, .mobile-brand small { color: #91a5bf; font-size: 9px; letter-spacing: .18em; }
.login-mark { width: 44px; height: 44px; display: grid; flex: 0 0 auto; place-items: center; border-radius: 11px; color: #fff; background: #2f6fed; box-shadow: 0 10px 24px rgba(47, 111, 237, .26); font-size: 20px; font-weight: 700; }
.brand-message { max-width: 470px; margin: auto 0; padding: 58px 0; }.section-kicker { display: inline-flex; align-items: center; gap: 8px; color: #78a8fb; font-size: 11px; font-weight: 700; letter-spacing: .18em; }.section-kicker::before { content: ""; width: 24px; height: 1px; background: currentColor; }.brand-message h1 { margin: 20px 0 18px; color: #f8fbff !important; font-size: clamp(34px, 3.3vw, 48px); line-height: 1.28; letter-spacing: -.035em; }.brand-message > p { max-width: 410px; margin: 0; color: #aebbd0; font-size: 15px; line-height: 1.85; }.capability-list { display: grid; gap: 13px; margin-top: 34px; }.capability-list span { display: flex; align-items: center; gap: 10px; color: #d8e1ef; font-size: 13px; }.capability-list .el-icon { width: 26px; height: 26px; border: 1px solid rgba(122, 168, 251, .3); border-radius: 7px; color: #78a8fb; background: rgba(47,111,237,.08); }
.brand-footer { display: flex; align-items: center; gap: 8px; color: #aebbd0; font-size: 11px; }.brand-footer small { margin-left: auto; color: #70839e; letter-spacing: .1em; }.security-dot { width: 7px; height: 7px; border-radius: 50%; background: #4cc38a; box-shadow: 0 0 0 4px rgba(76,195,138,.12); }
.form-panel { display: grid; align-content: center; min-width: 0; padding: 60px 68px 38px; background: #fffdf9; }.mobile-brand { display: none; }.login-card { width: 100%; max-width: 420px; margin: 0 auto; }.form-heading { margin-bottom: 34px; }.access-badge { width: fit-content; display: inline-flex; align-items: center; gap: 7px; min-height: 26px; padding: 0 10px; border: 1px solid #dce5f1; border-radius: 999px; color: #50627c; background: #f7f9fc; font-size: 11px; font-weight: 600; }.access-badge > span { width: 6px; height: 6px; border-radius: 50%; background: #34a56f; }.form-heading h2 { margin: 18px 0 9px; color: #172136; font-size: 32px; line-height: 1.2; letter-spacing: -.025em; }.form-heading p { margin: 0; color: #718096; font-size: 14px; line-height: 1.7; }
.login-card :deep(.el-form-item) { margin-bottom: 22px; }.login-card :deep(.el-form-item__label) { padding-bottom: 8px; color: #34445d; font-size: 13px; font-weight: 600; }.login-card :deep(.el-input__wrapper) { min-height: 48px; padding: 0 14px; border-radius: 10px; background: #fff; box-shadow: 0 0 0 1px #d7e0ec inset; }.login-card :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #aebed3 inset; }.login-card :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #2f6fed inset, 0 0 0 3px rgba(47,111,237,.1); }.login-card :deep(.el-input__prefix) { margin-right: 8px; color: #8b99ad; }.login-card :deep(.el-alert) { margin: -2px 0 18px; border-radius: 9px; }
.login-button { width: 100%; min-height: 48px; display: flex; margin-top: 5px; border: 0; border-radius: 10px; background: #245fc7; box-shadow: 0 10px 24px rgba(36,95,199,.2); font-weight: 600; letter-spacing: .04em; }.login-button:hover, .login-button:focus { background: #1d52b1; }.login-button :deep(span) { width: 100%; display: flex; align-items: center; justify-content: center; gap: 9px; }
.login-help { display: flex; align-items: center; justify-content: center; gap: 20px; margin-top: 23px; color: #7b899d; font-size: 11px; }.login-help span { display: inline-flex; align-items: center; gap: 5px; }.login-help .el-icon { color: #3aa574; }.form-footer { align-self: end; margin: 54px 0 0; color: #9aa5b5; text-align: center; font-size: 10px; }
@media (max-width: 900px) { .login-page { padding: 20px; }.login-shell { min-height: 620px; grid-template-columns: .85fr 1.15fr; }.brand-panel { padding: 36px; }.brand-message h1 { font-size: 32px; }.form-panel { padding: 48px 38px 32px; } }
@media (max-width: 700px) {
  .login-page { min-height: 100dvh; place-items: stretch; padding: 0; overflow: auto; background: #f6f8fb; }
  .login-shell { width: 100%; min-height: 100dvh; display: block; border: 0; border-radius: 0; background: #fffdf9; box-shadow: none; }
  .brand-panel { display: none; }
  .form-panel { min-height: 100dvh; display: flex; flex-direction: column; justify-content: flex-start; padding: 22px 20px 20px; }
  .mobile-brand { display: flex; margin-bottom: 42px; padding-bottom: 18px; border-bottom: 1px solid #e5eaf1; color: #172136; }
  .mobile-brand .login-mark { width: 40px; height: 40px; border-radius: 10px; font-size: 18px; }
  .mobile-brand small { color: #8190a5; }
  .login-card { max-width: 440px; }
  .form-heading { margin-bottom: 28px; }
  .form-heading h2 { margin-top: 14px; font-size: 30px; }
  .login-card :deep(.el-form-item) { margin-bottom: 18px; }
  .login-card :deep(.el-input__wrapper), .login-button { min-height: 50px; }
  .login-help { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 20px; }
  .login-help span { min-height: 38px; justify-content: center; padding: 0 8px; border: 1px solid #e1e7ef; border-radius: 9px; background: #fafbfd; white-space: nowrap; }
  .form-footer { align-self: stretch; margin: 0; margin-top: auto; padding-top: 36px; text-align: center; line-height: 1.6; }
}
@media (max-width: 380px) {
  .form-panel { padding-right: 16px; padding-left: 16px; }
  .mobile-brand { margin-bottom: 32px; }
  .login-help { grid-template-columns: 1fr; }
}
</style>
