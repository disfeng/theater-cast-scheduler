<template>
  <section class="ai-settings">
    <el-alert title="启用后，管理员提交的信息板原文（含玩家昵称和备注）会发送给所配置的外部服务。AI 结果仅生成待复核草稿。" type="warning" show-icon :closable="false" />
    <el-form v-if="loaded" label-position="top" @submit.prevent="save">
      <el-form-item label="启用智能解析"><el-switch v-model="form.enabled" /></el-form-item>
      <el-form-item label="API 地址"><el-input v-model="form.endpoint" /></el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="replacementKey" type="password" show-password placeholder="留空则保留现有密钥" autocomplete="new-password" />
        <small v-if="settings?.api_key_masked">已保存：{{ settings.api_key_masked }}</small>
      </el-form-item>
      <el-form-item label="模型名称"><el-input v-model="form.model_name" /></el-form-item>
      <el-form-item label="请求超时（秒）"><el-input-number v-model="form.timeout_seconds" :min="1" :max="300" /></el-form-item>
      <p>当前提示词版本：{{ settings?.prompt_version }}</p>
      <p v-if="settings?.last_test_message">最近测试：{{ settings.last_test_message }} {{ settings.last_tested_at || "" }}</p>
      <el-button type="primary" native-type="submit">保存 AI 配置</el-button>
      <el-button :loading="testing" @click="testConnection">测试连接</el-button>
    </el-form>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { adminApi, type AiParserSettings } from "../../api/admin";
import { useAuthStore } from "../../auth/store";
const auth = useAuthStore();
const loaded = ref(false), testing = ref(false), replacementKey = ref("");
const settings = ref<AiParserSettings>();
const form = reactive({ enabled: false, endpoint: "", model_name: "", timeout_seconds: 30 });
function applyWritable(value: AiParserSettings) { form.enabled = value.enabled; form.endpoint = value.endpoint; form.model_name = value.model_name; form.timeout_seconds = value.timeout_seconds; }
async function load() { settings.value = await adminApi.getAiParserSettings(auth.token as string); applyWritable(settings.value); loaded.value = true; }
async function save() { const payload: { enabled: boolean; endpoint: string; model_name: string; timeout_seconds: number; api_key?: string } = { enabled: form.enabled, endpoint: form.endpoint, model_name: form.model_name, timeout_seconds: form.timeout_seconds }; if (replacementKey.value.trim()) payload.api_key = replacementKey.value; settings.value = await adminApi.updateAiParserSettings(auth.token as string, payload); replacementKey.value = ""; applyWritable(settings.value); }
async function testConnection() { testing.value = true; try { await adminApi.testAiParserConnection(auth.token as string); await load(); } finally { testing.value = false; } }
onMounted(load);
</script>

<style scoped>.ai-settings { max-width: 720px; display: grid; gap: 18px; }.ai-settings small,.ai-settings p { color: var(--text-secondary); }</style>
