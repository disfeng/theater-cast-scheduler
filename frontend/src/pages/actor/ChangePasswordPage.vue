<template>
  <main class="password-page">
    <section class="password-card">
      <div class="brand-mark">剧</div>
      <div class="page-copy">
        <el-tag type="warning" effect="light" round>账号安全</el-tag>
        <h1>首次登录，请修改密码</h1>
        <p>初始密码仅用于账号交付。设置新密码后，才能进入演员工作台。</p>
      </div>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="当前密码">
          <el-input v-model="currentPassword" aria-label="当前密码" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="newPassword" aria-label="新密码" type="password" autocomplete="new-password" show-password />
          <small>至少 10 位，建议同时包含字母和数字</small>
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="confirmedPassword" aria-label="确认新密码" type="password" autocomplete="new-password" show-password />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
        <el-button class="submit-button" type="primary" native-type="submit" :loading="submitting">确认修改</el-button>
      </el-form>

      <button class="logout-link" type="button" @click="logout">退出并返回登录</button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { actorApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";

const router = useRouter();
const authStore = useAuthStore();
const currentPassword = ref("");
const newPassword = ref("");
const confirmedPassword = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  if (newPassword.value.length < 10) { error.value = "新密码至少需要 10 位"; return; }
  if (newPassword.value !== confirmedPassword.value) { error.value = "两次输入的新密码不一致"; return; }
  if (!authStore.token) { logout(); return; }
  submitting.value = true;
  try {
    const session = await actorApi.changePassword(authStore.token, {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    });
    authStore.setSession(session.access_token, session.role, session.must_change_password);
    await router.replace("/actor/schedule");
  } catch (cause: any) {
    error.value = cause?.message === "current_password_invalid" ? "当前密码不正确" : cause?.message || "密码修改失败，请稍后重试";
  } finally {
    submitting.value = false;
  }
}

function logout() {
  authStore.logout();
  router.replace("/login");
}
</script>

<style scoped>
.password-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: linear-gradient(160deg, #edf4ff 0%, #f7f9fc 58%, #eef3f8 100%); }
.password-card { width: min(100%, 430px); padding: 30px; border: 1px solid #dfe6f0; border-radius: 20px; background: rgba(255,255,255,.96); box-shadow: 0 20px 50px rgba(40,61,95,.12); }
.brand-mark { width: 48px; height: 48px; display: grid; place-items: center; margin-bottom: 24px; border-radius: 13px; color: #fff; background: #2f6fed; font-size: 24px; font-weight: 700; }
.page-copy { margin-bottom: 24px; }
.page-copy h1 { margin: 14px 0 8px; color: #18233a; font-size: 26px; line-height: 1.25; }
.page-copy p { margin: 0; color: #6f7b91; font-size: 14px; line-height: 1.7; }
.password-card :deep(.el-form-item) { margin-bottom: 18px; }
.password-card :deep(.el-form-item__label) { color: #475467; font-weight: 600; }
.password-card :deep(.el-input__wrapper) { min-height: 44px; }
.password-card small { margin-top: 7px; color: #98a2b3; font-size: 12px; }
.password-card :deep(.el-alert) { margin-bottom: 18px; }
.submit-button { width: 100%; min-height: 44px; }
.logout-link { width: 100%; margin-top: 18px; border: 0; color: #7a8699; background: transparent; cursor: pointer; }
@media (max-width: 520px) { .password-page { padding: 16px; align-items: center; } .password-card { padding: 24px 20px; border-radius: 16px; } }
</style>
