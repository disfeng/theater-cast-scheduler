<template>
  <div class="actor-viewport">
    <div class="actor-phone-shell">
      <header class="actor-topbar">
        <strong>剧场卡司</strong>
        <span>{{ profile?.display_name || "演员工作台" }}</span>
      </header>
      <main class="actor-content"><RouterView /></main>
      <nav class="actor-tabs" aria-label="演员端导航">
        <RouterLink to="/actor/schedule"><el-icon><HomeFilled /></el-icon><span>工作台</span></RouterLink>
        <RouterLink to="/actor/calendar"><el-icon><Calendar /></el-icon><span>演出日历</span></RouterLink>
        <RouterLink to="/actor/leave"><el-icon><Document /></el-icon><span>我的请假</span></RouterLink>
        <RouterLink to="/actor/profile"><el-icon><User /></el-icon><span>我的</span></RouterLink>
      </nav>
      <div class="watermark" aria-hidden="true">
        <span v-for="index in 18" :key="index">{{ watermark }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Calendar, Document, HomeFilled, User } from "@element-plus/icons-vue";
import { actorApi } from "../api/admin";
import { useAuthStore } from "../auth/store";

const auth = useAuthStore();
const profile = ref<{ display_name: string; phone_number: string } | null>(null);
const now = ref(new Date());
let timer: number | undefined;
const maskedPhone = computed(() => profile.value?.phone_number?.replace(/^(\d{3})\d+(\d{4})$/, "$1****$2") || "");
const watermark = computed(() => `${profile.value?.display_name || "演员"} ${maskedPhone.value} ${now.value.toLocaleString("zh-CN", { hour12: false })}`);

onMounted(async () => {
  if (auth.token) {
    try { profile.value = await actorApi.getProfile(auth.token); } catch { /* page handles API failures */ }
  }
  timer = window.setInterval(() => { now.value = new Date(); }, 60_000);
});
onBeforeUnmount(() => timer && window.clearInterval(timer));
</script>

<style scoped>
.actor-viewport { min-height: 100vh; background: #273142; }
.actor-phone-shell { position: relative; width: min(100%, 480px); min-height: 100vh; margin: 0 auto; background: #f4f7fb; overflow: hidden; }
.actor-topbar { position: sticky; top: 0; z-index: 5; height: 58px; padding: 0 18px; display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,.96); border-bottom: 1px solid #e4eaf2; }
.actor-topbar strong { color: #182236; font-size: 17px; }
.actor-topbar span { color: #718096; font-size: 13px; }
.actor-content { position: relative; z-index: 2; min-height: calc(100vh - 130px); padding: 20px 16px 94px; }
.actor-tabs { position: fixed; z-index: 7; bottom: 0; left: 50%; width: min(100%, 480px); transform: translateX(-50%); display: grid; grid-template-columns: repeat(4, 1fr); padding: 8px 8px calc(8px + env(safe-area-inset-bottom)); background: rgba(255,255,255,.97); border-top: 1px solid #e4eaf2; box-shadow: 0 -8px 24px rgba(24,34,54,.06); }
.actor-tabs a { display: flex; min-height: 48px; align-items: center; justify-content: center; flex-direction: column; gap: 3px; color: #8490a3; font-size: 11px; border-radius: 12px; }
.actor-tabs a.router-link-active { color: #2f6fed; background: #edf4ff; }
.actor-tabs .el-icon { font-size: 20px; }
.watermark { pointer-events: none; position: fixed; z-index: 3; inset: 58px calc((100vw - min(100vw, 480px))/2) 70px; display: grid; grid-template-columns: repeat(3, 1fr); align-content: space-around; overflow: hidden; opacity: .055; transform: rotate(-20deg) scale(1.25); }
.watermark span { color: #172238; font-size: 11px; white-space: nowrap; margin: 28px 8px; }
@media (min-width: 481px) { .actor-phone-shell { box-shadow: 0 0 0 1px rgba(255,255,255,.08), 0 24px 60px rgba(0,0,0,.22); } }
</style>
