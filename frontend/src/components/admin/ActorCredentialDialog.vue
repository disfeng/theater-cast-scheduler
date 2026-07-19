<template>
  <el-dialog
    :model-value="modelValue"
    title="演员账号已创建"
    width="620px"
    class="credential-dialog app-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="delivery" class="credential-content">
      <div class="success-mark">✓</div>
      <div>
        <h3>账号凭证仅显示本次</h3>
        <p>请下载 PDF 并安全交付给演员，关闭后不再显示初始密码。</p>
      </div>
      <dl>
        <div><dt>用户名</dt><dd>{{ delivery.username }}</dd></div>
        <div><dt>初始密码</dt><dd>{{ delivery.initial_password }}</dd></div>
      </dl>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">已安全交付</el-button>
      <el-button type="primary" @click="downloadPdf">下载账号 PDF</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import type { ActorCredentialDelivery } from "../../api/admin";

const props = defineProps<{ modelValue: boolean; delivery: ActorCredentialDelivery | null }>();
const emit = defineEmits<{ (event: "update:modelValue", value: boolean): void }>();

function downloadPdf() {
  if (!props.delivery) return;
  const bytes = Uint8Array.from(atob(props.delivery.pdf_base64), (char) => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = props.delivery.filename;
  link.click();
  URL.revokeObjectURL(url);
}
</script>

<style scoped>
.credential-content { display: grid; grid-template-columns: 52px 1fr; gap: 18px; }
.success-mark { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 15px; background: #eaf8f1; color: #16a36a; font-size: 25px; font-weight: 800; }
h3 { margin: 3px 0 7px; font-size: 20px; } p { margin: 0; color: var(--text-secondary); line-height: 1.7; }
dl { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 8px 0 0; }
dl div { padding: 16px; border: 1px solid #e5eaf2; border-radius: 12px; background: #f8faff; }
dt { color: var(--text-secondary); font-size: 13px; margin-bottom: 7px; } dd { margin: 0; font-size: 17px; font-weight: 650; letter-spacing: .02em; }
</style>
