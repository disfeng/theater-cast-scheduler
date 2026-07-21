<template>
  <section class="profile-page">
    <header class="page-heading">
      <span class="eyebrow">个人中心</span>
      <h1>我的</h1>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <section class="identity-card" :class="{ loading }">
      <div class="avatar">{{ avatarText }}</div>
      <div class="identity-copy">
        <div class="name-line">
          <strong>{{ profile?.display_name || "演员" }}</strong>
          <span class="account-status"><i></i>账号正常</span>
        </div>
        <span class="phone">{{ maskedPhone || "手机号未完善" }}</span>
      </div>
    </section>

    <section class="profile-section">
      <div class="section-heading">
        <div>
          <h2>所属剧场</h2>
          <p>你的排班与请假将按剧场分开管理</p>
        </div>
        <span>{{ profile?.theaters.length || 0 }} 个</span>
      </div>
      <div v-if="profile?.theaters.length" class="theater-list">
        <div v-for="theater in profile.theaters" :key="theater.id" class="theater-row">
          <span class="theater-icon"><el-icon><OfficeBuilding /></el-icon></span>
          <div><strong>{{ theater.name }}</strong><small>{{ theater.is_entry_theater ? "默认排班剧场" : "已加入剧场" }}</small></div>
          <em v-if="theater.is_entry_theater">主剧场</em>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-line">暂未关联剧场</div>
    </section>

    <section class="profile-section shortcut-section">
      <div class="section-heading compact"><div><h2>常用功能</h2></div></div>
      <nav class="shortcut-list" aria-label="我的常用功能">
        <RouterLink to="/actor/change-password">
          <span class="shortcut-icon blue"><el-icon><Lock /></el-icon></span>
          <span><strong>修改密码</strong><small>定期更换密码，保护账号安全</small></span>
          <el-icon class="arrow"><ArrowRight /></el-icon>
        </RouterLink>
        <RouterLink to="/actor/calendar">
          <span class="shortcut-icon violet"><el-icon><Calendar /></el-icon></span>
          <span><strong>演出日历</strong><small>查看已披露的演出安排</small></span>
          <el-icon class="arrow"><ArrowRight /></el-icon>
        </RouterLink>
        <RouterLink to="/actor/leave">
          <span class="shortcut-icon amber"><el-icon><Document /></el-icon></span>
          <span><strong>我的请假</strong><small>提交请假并跟踪审批结果</small></span>
          <el-icon class="arrow"><ArrowRight /></el-icon>
        </RouterLink>
      </nav>
    </section>

    <section class="security-note">
      <span><el-icon><CircleCheck /></el-icon></span>
      <div><strong>页面已启用动态水印</strong><p>请勿截图或向他人透露排班、玩家及指定信息。</p></div>
    </section>

    <button class="logout-button" type="button" @click="logout">退出登录</button>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, Calendar, CircleCheck, Document, Lock, OfficeBuilding } from "@element-plus/icons-vue";
import { actorApi } from "../../api/admin";
import { useAuthStore } from "../../auth/store";

type ActorProfile = {
  id: number;
  display_name: string;
  phone_number: string;
  must_change_password: boolean;
  theaters: { id: number; name: string; is_entry_theater: boolean }[];
};

const auth = useAuthStore();
const router = useRouter();
const profile = ref<ActorProfile | null>(null);
const loading = ref(true);
const error = ref("");
const maskedPhone = computed(() => profile.value?.phone_number?.replace(/^(\d{3})\d+(\d{4})$/, "$1****$2") || "");
const avatarText = computed(() => profile.value?.display_name?.slice(0, 1) || "演");

onMounted(async () => {
  if (!auth.token) return;
  try {
    profile.value = await actorApi.getProfile(auth.token) as ActorProfile;
  } catch (cause: any) {
    error.value = cause?.message || "个人信息加载失败";
  } finally {
    loading.value = false;
  }
});

function logout() {
  auth.logout();
  void router.replace("/login");
}
</script>

<style scoped>
.profile-page { color: #182236; }
.page-heading { margin-bottom: 17px; }
.eyebrow { color: #2f6fed; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.page-heading h1 { margin: 5px 0 0; font-size: 28px; line-height: 1.25; }
.profile-page :deep(.el-alert) { margin-bottom: 12px; }
.identity-card { position: relative; display: flex; align-items: center; gap: 15px; min-height: 96px; padding: 18px; margin-bottom: 13px; overflow: hidden; border: 1px solid #d7e3f5; border-radius: 20px; background: linear-gradient(135deg, #ffffff 12%, #edf4ff 100%); box-shadow: 0 8px 24px rgba(47,111,237,.08); }
.identity-card::after { content: ""; position: absolute; width: 110px; height: 110px; right: -35px; top: -54px; border-radius: 50%; border: 22px solid rgba(47,111,237,.07); }
.avatar { position: relative; z-index: 1; display: grid; place-items: center; flex: 0 0 58px; height: 58px; border-radius: 18px; color: #fff; background: linear-gradient(145deg, #4f86f7, #2865e5); box-shadow: 0 9px 20px rgba(47,111,237,.23); font-size: 23px; font-weight: 800; }
.identity-copy { position: relative; z-index: 1; min-width: 0; flex: 1; }
.name-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.name-line strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 21px; }
.account-status { flex: none; display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; border-radius: 999px; color: #168957; background: rgba(28,181,108,.09); font-size: 10px; font-weight: 700; }
.account-status i { width: 6px; height: 6px; border-radius: 50%; background: #20ad6c; }
.phone { display: block; margin-top: 8px; color: #718096; font-size: 14px; letter-spacing: .04em; }
.profile-section { padding: 17px; margin-bottom: 13px; border: 1px solid #e0e7f1; border-radius: 18px; background: rgba(255,255,255,.94); box-shadow: 0 5px 17px rgba(38,53,79,.04); }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 13px; }
.section-heading h2 { margin: 0; font-size: 16px; }
.section-heading p { margin: 5px 0 0; color: #8a96a8; font-size: 11px; line-height: 1.5; }
.section-heading > span { flex: none; padding: 3px 8px; border-radius: 999px; color: #2f6fed; background: #edf4ff; font-size: 10px; font-weight: 700; }
.section-heading.compact { margin-bottom: 8px; }
.theater-list { display: flex; flex-direction: column; gap: 8px; }
.theater-row { display: grid; grid-template-columns: 38px 1fr auto; align-items: center; gap: 10px; padding: 10px; border-radius: 13px; background: #f7f9fc; }
.theater-icon { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; color: #2f6fed; background: #e8f1ff; }
.theater-row div { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.theater-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.theater-row small { color: #98a2b3; font-size: 10px; }
.theater-row em { padding: 3px 7px; border: 1px solid #cfe0fb; border-radius: 999px; color: #2f6fed; background: #fff; font-size: 9px; font-style: normal; font-weight: 700; }
.empty-line { padding: 15px; border-radius: 12px; color: #98a2b3; background: #f8fafc; text-align: center; font-size: 12px; }
.shortcut-section { padding-bottom: 7px; }
.shortcut-list { display: flex; flex-direction: column; }
.shortcut-list a { display: grid; grid-template-columns: 36px 1fr 16px; align-items: center; gap: 11px; min-height: 58px; border-top: 1px solid #edf1f6; color: inherit; text-decoration: none; }
.shortcut-list a:first-child { border-top: 0; }
.shortcut-icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; font-size: 16px; }
.shortcut-icon.blue { color: #2f6fed; background: #eaf2ff; }.shortcut-icon.violet { color: #7658d9; background: #f0edff; }.shortcut-icon.amber { color: #c57914; background: #fff4df; }
.shortcut-list a > span:nth-child(2) { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.shortcut-list strong { font-size: 13px; }.shortcut-list small { overflow: hidden; color: #98a2b3; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.shortcut-list .arrow { color: #b6bfcc; }
.security-note { display: flex; gap: 11px; padding: 14px 15px; margin-bottom: 13px; border: 1px solid #dce8f7; border-radius: 16px; background: #f5f9ff; }
.security-note > span { display: grid; place-items: center; flex: 0 0 30px; height: 30px; border-radius: 50%; color: #2f6fed; background: #e5efff; }
.security-note strong { font-size: 12px; }.security-note p { margin: 4px 0 0; color: #7d899c; font-size: 10px; line-height: 1.55; }
.logout-button { width: 100%; min-height: 44px; border: 1px solid #dbe2ec; border-radius: 13px; color: #667085; background: rgba(255,255,255,.86); font-size: 13px; font-weight: 600; cursor: pointer; }
.logout-button:active { background: #f1f4f8; }
.loading { opacity: .65; }
</style>
