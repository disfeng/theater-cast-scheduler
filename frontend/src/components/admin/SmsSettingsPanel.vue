<template>
  <div class="sms-settings" :class="{ 'theater-only': !isSuperAdmin }">
    <section v-if="isSuperAdmin" class="settings-section global-settings">
      <div class="section-heading">
        <div><strong>短信服务</strong><span>仅提醒演员登录工作台，不包含任何演出信息</span></div>
        <div class="switch-control" :class="{ enabled: globalForm.sms_enabled }">
          <i aria-hidden="true"></i>
          <span>{{ globalForm.sms_enabled ? '短信服务已启用' : '短信服务已关闭' }}</span>
          <el-switch v-model="globalForm.sms_enabled" aria-label="短信全局开关" />
        </div>
      </div>
      <el-form label-position="top" class="settings-grid">
        <el-form-item label="演员端入口"><el-input v-model="globalForm.actor_portal_url" /></el-form-item>
        <el-form-item label="AccessKey ID"><el-input v-model="accessKeyId" :placeholder="globalForm.access_key_id_masked || '请输入 AccessKey ID'" /></el-form-item>
        <el-form-item label="AccessKey Secret"><el-input v-model="accessKeySecret" type="password" show-password placeholder="已保存的密钥不会回显" /></el-form-item>
        <el-form-item label="短信签名"><el-input v-model="globalForm.sign_name" /></el-form-item>
        <el-form-item label="模板编号"><el-input v-model="globalForm.template_code" /></el-form-item>
        <el-form-item label="服务端点"><el-input v-model="globalForm.endpoint" /></el-form-item>
      </el-form>
      <div class="actions"><el-button type="primary" @click="saveGlobal">保存全局设置</el-button></div>
    </section>

    <section v-if="theaterId" class="settings-section theater-policy">
      <div class="section-heading policy-heading">
        <div><strong>当前剧场披露策略</strong><span>按上海时区计算演出信息开放时间</span></div>
        <div class="switch-control" :class="{ enabled: theaterForm.sms_enabled }">
          <i aria-hidden="true"></i>
          <span>{{ theaterForm.sms_enabled ? '剧场短信已启用' : '剧场短信已关闭' }}</span>
          <el-switch v-model="theaterForm.sms_enabled" aria-label="剧场短信开关" />
        </div>
      </div>
      <div class="policy-row">
        <el-form inline class="policy-form">
          <el-form-item label="提前天数"><el-input-number v-model="theaterForm.reveal_days_before" aria-label="提前天数" :min="0" :max="30" /></el-form-item>
          <el-form-item label="通知时间"><el-time-picker v-model="theaterForm.reveal_time" value-format="HH:mm:ss" format="HH:mm" /></el-form-item>
        </el-form>
        <el-button type="primary" @click="saveTheater">保存剧场策略</el-button>
      </div>
    </section>

    <section v-if="isSuperAdmin" class="settings-section connectivity-section">
      <div class="connectivity-copy"><strong>短信连通性</strong><span>测试号码不会保存</span></div>
      <div class="test-row"><el-input v-model="testPhone" placeholder="输入测试手机号" /><el-button type="primary" aria-label="发送测试短信" :disabled="!globalForm.sms_enabled" @click="sendTest">发送测试短信</el-button></div>
    </section>

    <section v-if="isSuperAdmin" class="settings-section logs-section">
      <div class="section-heading"><div><strong>发送日志</strong><span>手机号已脱敏，日志不包含排班内容</span></div></div>
      <div role="table" aria-label="短信发送日志">
      <el-table :data="logs" empty-text="暂无短信发送记录">
        <el-table-column prop="theater_id" label="剧场" width="90" />
        <el-table-column prop="actor_id" label="演员" width="90" />
        <el-table-column prop="masked_phone" label="手机号" width="140" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="attempt_count" label="尝试" width="80" />
        <el-table-column prop="provider_request_id" label="服务回执" min-width="150" />
        <el-table-column prop="failure_reason" label="失败原因" min-width="180" />
      </el-table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { adminApi, type ActorNotificationSettings, type SmsDeliveryLog, type TheaterActorNotificationSettings } from "../../api/admin";

const props = withDefaults(defineProps<{ token: string; theaterId?: number; isSuperAdmin?: boolean }>(), { isSuperAdmin: true });
const globalForm = reactive<ActorNotificationSettings>({ sms_enabled: false, actor_portal_url: "http://localhost:7003/actor", credentials_configured: false, access_key_id_masked: null, sign_name: null, template_code: null, endpoint: "dysmsapi.aliyuncs.com" });
const theaterForm = reactive<TheaterActorNotificationSettings>({ reveal_days_before: 1, reveal_time: "21:00:00", sms_enabled: false });
const accessKeyId = ref(""), accessKeySecret = ref(""), testPhone = ref("");
const logs = ref<SmsDeliveryLog[]>([]);

async function load() {
  if (props.isSuperAdmin) {
    const [settings, deliveries] = await Promise.all([adminApi.getActorNotificationSettings(props.token), adminApi.getActorNotificationSmsLogs(props.token)]);
    Object.assign(globalForm, settings); logs.value = deliveries;
  }
  if (props.theaterId) Object.assign(theaterForm, await adminApi.getTheaterActorNotificationSettings(props.token, props.theaterId));
}
async function saveGlobal() {
  const payload: Record<string, unknown> = { sms_enabled: globalForm.sms_enabled, actor_portal_url: globalForm.actor_portal_url, sign_name: globalForm.sign_name, template_code: globalForm.template_code, endpoint: globalForm.endpoint };
  if (accessKeyId.value) payload.access_key_id = accessKeyId.value;
  if (accessKeySecret.value) payload.access_key_secret = accessKeySecret.value;
  Object.assign(globalForm, await adminApi.updateActorNotificationSettings(props.token, payload));
  accessKeyId.value = ""; accessKeySecret.value = ""; ElMessage.success("全局通知设置已保存");
}
async function saveTheater() { if (!props.theaterId) return; await adminApi.updateTheaterActorNotificationSettings(props.token, props.theaterId, { ...theaterForm }); ElMessage.success("剧场披露策略已保存"); }
async function sendTest() { await adminApi.testActorNotificationSms(props.token, testPhone.value); testPhone.value = ""; ElMessage.success("测试短信已提交"); }
watch(() => props.theaterId, () => load());
onMounted(load);
</script>

<style scoped>
.sms-settings { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(420px, .85fr); gap: 12px; align-items: stretch; }
.global-settings { grid-column: 1; grid-row: 1 / 3; }
.theater-policy { grid-column: 2; grid-row: 1; }
.connectivity-section { grid-column: 2; grid-row: 2; }
.logs-section { grid-column: 1 / -1; }
.sms-settings.theater-only { grid-template-columns: 1fr; }
.sms-settings.theater-only .theater-policy { grid-column: 1; grid-row: 1; }
.settings-section { padding: 16px 18px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 12px; }
.section-heading > div { display: grid; gap: 4px; }
.section-heading strong, .connectivity-copy strong { font-size: 16px; color: var(--text-primary); }
.section-heading span { color: var(--text-secondary); font-size: 13px; }
.switch-control { display: flex !important; grid-auto-flow: column; align-items: center; gap: 8px !important; }
.switch-control i { width: 7px; height: 7px; border-radius: 50%; background: #aab2c0; }
.switch-control span { color: #7b8495; font-size: 12px; font-weight: 600; white-space: nowrap; }
.switch-control.enabled i { background: #24a36a; box-shadow: 0 0 0 4px #e5f6ed; }
.switch-control.enabled span { color: #178b57; }
.switch-control :deep(.el-switch) { --el-switch-on-color: #24a36a; --el-switch-off-color: #c4cad5; }
.switch-control :deep(.el-switch__core) { min-width: 40px; }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.settings-grid :deep(.el-form-item) { margin-bottom: 12px; }
.settings-grid :deep(.el-form-item__label) { height: 24px; padding-bottom: 5px; color: #667085; font-size: 13px; line-height: 19px; }
.settings-grid :deep(.el-input__wrapper), .test-row :deep(.el-input__wrapper) { min-height: 38px; }
.policy-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.policy-form { display: flex; align-items: end; gap: 12px; }
.policy-form :deep(.el-form-item) { margin: 0; }
.policy-form :deep(.el-form-item__label) { color: #667085; font-size: 13px; }
.policy-form :deep(.el-input-number) { width: 150px; }
.policy-form :deep(.el-date-editor) { width: 180px; }
.actions { display: flex; justify-content: flex-end; }
.connectivity-section { display: grid; grid-template-columns: 150px minmax(0, 1fr); align-items: center; gap: 18px; }
.connectivity-copy { display: grid; gap: 3px; }
.connectivity-copy span { color: var(--text-secondary); font-size: 13px; }
.test-row { display: grid; grid-template-columns: minmax(220px, 1fr) auto; gap: 8px; }
.settings-section :deep(.el-button) { min-height: 38px; }
.settings-section:last-child .section-heading { margin-bottom: 10px; }
.settings-section:last-child :deep(.el-table) { font-size: 13px; }
@media (max-width: 900px) {
  .sms-settings { grid-template-columns: 1fr; }
  .global-settings, .theater-policy, .connectivity-section, .logs-section { grid-column: 1; grid-row: auto; }
  .settings-grid { grid-template-columns: 1fr; }
  .policy-row, .connectivity-section { align-items: stretch; grid-template-columns: 1fr; flex-direction: column; }
  .policy-form { flex-wrap: wrap; }
  .test-row { grid-template-columns: 1fr auto; }
}
</style>
