<template>
  <div class="sms-settings">
    <section class="settings-section">
      <div class="section-heading">
        <div><strong>演员通知与短信</strong><span>短信仅提醒登录工作台，不包含任何演出信息</span></div>
        <el-switch v-model="globalForm.sms_enabled" aria-label="短信全局开关" active-text="全局启用" />
      </div>
      <el-form label-position="top" class="settings-grid">
        <el-form-item label="演员端入口"><el-input v-model="globalForm.actor_portal_url" /></el-form-item>
        <el-form-item label="AccessKey ID"><el-input v-model="accessKeyId" :placeholder="globalForm.access_key_id_masked || '请输入 AccessKey ID'" /></el-form-item>
        <el-form-item label="AccessKey Secret"><el-input v-model="accessKeySecret" type="password" show-password placeholder="已保存的密钥不会回显" /></el-form-item>
        <el-form-item label="短信签名"><el-input v-model="globalForm.sign_name" /></el-form-item>
        <el-form-item label="模板编号"><el-input v-model="globalForm.template_code" /></el-form-item>
        <el-form-item label="服务端点"><el-input v-model="globalForm.endpoint" /></el-form-item>
      </el-form>
      <div class="actions"><el-button @click="saveGlobal">保存全局设置</el-button></div>
    </section>

    <section v-if="theaterId" class="settings-section theater-policy">
      <div class="section-heading"><div><strong>当前剧场披露策略</strong><span>按上海时区计算演出信息开放时间</span></div><el-switch v-model="theaterForm.sms_enabled" active-text="剧场短信" /></div>
      <el-form inline class="policy-form">
        <el-form-item label="提前天数"><el-input-number v-model="theaterForm.reveal_days_before" aria-label="提前天数" :min="0" :max="30" /></el-form-item>
        <el-form-item label="通知时间"><el-time-picker v-model="theaterForm.reveal_time" value-format="HH:mm:ss" format="HH:mm" /></el-form-item>
      </el-form>
      <div class="actions"><el-button type="primary" @click="saveTheater">保存剧场策略</el-button></div>
    </section>

    <section class="settings-section">
      <div class="section-heading"><div><strong>短信连通性</strong><span>测试号码不会保存</span></div></div>
      <div class="test-row"><el-input v-model="testPhone" placeholder="输入测试手机号" /><el-button type="primary" aria-label="发送测试短信" @click="sendTest">发送测试短信</el-button></div>
    </section>

    <section class="settings-section">
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

const props = defineProps<{ token: string; theaterId?: number }>();
const globalForm = reactive<ActorNotificationSettings>({ sms_enabled: false, actor_portal_url: "http://localhost:7003/actor", credentials_configured: false, access_key_id_masked: null, sign_name: null, template_code: null, endpoint: "dysmsapi.aliyuncs.com" });
const theaterForm = reactive<TheaterActorNotificationSettings>({ reveal_days_before: 1, reveal_time: "21:00:00", sms_enabled: false });
const accessKeyId = ref(""), accessKeySecret = ref(""), testPhone = ref("");
const logs = ref<SmsDeliveryLog[]>([]);

async function load() {
  const [settings, deliveries] = await Promise.all([adminApi.getActorNotificationSettings(props.token), adminApi.getActorNotificationSmsLogs(props.token)]);
  Object.assign(globalForm, settings); logs.value = deliveries;
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
.sms-settings { display: grid; gap: 16px; }
.settings-section { padding: 20px; border: 1px solid #e5eaf2; border-radius: 14px; background: #fff; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
.section-heading > div { display: grid; gap: 4px; }
.section-heading strong { font-size: 17px; color: var(--text-primary); }
.section-heading span { color: var(--text-secondary); font-size: 13px; }
.settings-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 16px; }
.policy-form { display: flex; align-items: end; gap: 14px; }
.actions { display: flex; justify-content: flex-end; }
.test-row { display: grid; grid-template-columns: minmax(240px, 420px) auto; justify-content: start; gap: 10px; }
@media (max-width: 900px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
