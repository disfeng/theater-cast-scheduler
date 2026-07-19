<template>
  <el-drawer
    :model-value="modelValue"
    :title="actor ? '编辑演员' : '新增演员'"
    size="560px"
    class="actor-drawer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert v-if="saveError" :title="saveError" type="error" show-icon :closable="false" class="drawer-error" />

    <el-form label-position="top" class="actor-form" @submit.prevent="save">
      <div class="form-grid">
        <el-form-item label="演员姓名" class="wide-field">
          <el-input v-model="displayName" aria-label="演员姓名" placeholder="例如：小展" :disabled="Boolean(actor)" />
        </el-form-item>
        <el-form-item label="手机号" required>
          <el-input v-model="phoneNumber" aria-label="手机号" inputmode="tel" :required="!actor" placeholder="11 位手机号" />
        </el-form-item>
        <el-form-item label="入职剧场" required>
          <el-select v-model="entryTheaterId" aria-label="入职剧场" placeholder="请选择入职剧场">
            <el-option v-for="theater in assignedTheaters" :key="theater.id" :label="theater.name" :value="theater.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="演员评级">
          <el-select v-model="ratingLevel" aria-label="演员评级">
            <el-option label="高" value="high" />
            <el-option label="普通" value="normal" />
            <el-option label="低" value="low" />
            <el-option label="暂停" value="suspended" />
          </el-select>
        </el-form-item>
        <el-form-item label="最大连场">
          <el-input-number v-model="maxConsecutive" aria-label="最大连场" :min="1" :max="3" controls-position="right" />
        </el-form-item>
        <el-form-item label="低评级月度上限">
          <el-input-number v-model="monthlyCap" aria-label="低评级月度上限" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="notes" aria-label="备注" placeholder="可选" />
        </el-form-item>
      </div>

      <section class="membership-section">
        <div class="section-title"><strong>所属剧场</strong><span>可同时在多个剧场工作</span></div>
        <el-checkbox-group v-model="theaterIds" class="theater-options">
          <el-checkbox v-for="theater in theaters" :key="theater.id" :value="theater.id" :aria-label="`所属剧场：${theater.name}`" border>{{ theater.name }}</el-checkbox>
        </el-checkbox-group>
      </section>

      <section class="capability-section">
        <div class="section-title"><strong>可出演角色</strong><span>按剧场配置演员的角色能力</span></div>
        <el-empty v-if="roleGroups.length === 0" description="暂无可配置角色" :image-size="64" />
        <div v-for="group in roleGroups" :key="group.theater.id" class="theater-role-group">
          <div class="group-heading">
            <strong>{{ group.theater.name }}</strong>
            <div>
              <el-button text type="primary" :aria-label="`${group.theater.name}全选`" @click="selectGroup(group.roles)">全选</el-button>
              <el-button text :aria-label="`${group.theater.name}清空`" @click="clearGroup(group.roles)">清空</el-button>
            </div>
          </div>
          <el-checkbox-group v-model="selectedRoleIds" class="role-options">
            <el-checkbox
              v-for="role in group.roles"
              :key="role.id"
              :value="role.id"
              :aria-label="`${group.theater.name}：${role.name}`"
              border
            >{{ role.name }}</el-checkbox>
          </el-checkbox-group>
        </div>
      </section>
    </el-form>

    <template #footer>
      <el-button :disabled="saving" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSave" @click="save">保存演员</el-button>
    </template>
</el-drawer>
  <ActorCredentialDialog v-model="credentialOpen" :delivery="credentialDelivery" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { adminApi, type Actor, type Role, type Theater } from "../../api/admin";
import type { ActorCredentialDelivery } from "../../api/admin";
import ActorCredentialDialog from "./ActorCredentialDialog.vue";

const props = defineProps<{ modelValue: boolean; actor: Actor | null; roles: Role[]; theaters: Theater[]; token: string }>();
const emit = defineEmits<{ (event: "update:modelValue", value: boolean): void; (event: "saved"): void; (event: "error", value: string): void }>();

const displayName = ref("");
const phoneNumber = ref("");
const theaterIds = ref<number[]>([]);
const entryTheaterId = ref<number | null>(null);
const ratingLevel = ref<Actor["rating_level"]>("normal");
const maxConsecutive = ref(3);
const monthlyCap = ref<number | null>(null);
const notes = ref("");
const selectedRoleIds = ref<number[]>([]);
const saving = ref(false);
const saveError = ref("");
const createdActorId = ref<number | null>(null);
const credentialDelivery = ref<ActorCredentialDelivery | null>(null);
const credentialOpen = ref(false);

const roleGroups = computed(() => props.theaters
  .map((theater) => ({ theater, roles: props.roles.filter((role) => role.theater_id === theater.id && role.is_active) }))
  .filter((group) => group.roles.length > 0));
const assignedTheaters = computed(() => props.theaters.filter((theater) => theaterIds.value.includes(theater.id)));
const canSave = computed(() => Boolean(displayName.value.trim() && (props.actor || (phoneNumber.value.trim() && entryTheaterId.value && theaterIds.value.length))));

watch(theaterIds, () => {
  if (entryTheaterId.value && !theaterIds.value.includes(entryTheaterId.value)) entryTheaterId.value = null;
});

watch(selectedRoleIds, (roleIds) => {
  const roleTheaterIds = props.roles.filter((role) => roleIds.includes(role.id)).map((role) => role.theater_id);
  theaterIds.value = Array.from(new Set([...theaterIds.value, ...roleTheaterIds]));
  if (!entryTheaterId.value && theaterIds.value.length === 1) entryTheaterId.value = theaterIds.value[0];
});

watch(() => props.modelValue, (open, wasOpen) => {
  if (!open || wasOpen) return;
  displayName.value = props.actor?.display_name || "";
  phoneNumber.value = props.actor?.phone_number || "";
  theaterIds.value = [...(props.actor?.theater_ids || [])];
  entryTheaterId.value = props.actor?.entry_theater_id || null;
  ratingLevel.value = props.actor?.rating_level || "normal";
  maxConsecutive.value = props.actor?.max_consecutive_performances || 3;
  monthlyCap.value = props.actor?.low_rating_monthly_cap ?? null;
  notes.value = props.actor?.notes || "";
  selectedRoleIds.value = [...(props.actor?.role_ids || [])];
  createdActorId.value = null;
  saveError.value = "";
});

function selectGroup(roles: Role[]) {
  selectedRoleIds.value = Array.from(new Set([...selectedRoleIds.value, ...roles.map((role) => role.id)]));
}

function clearGroup(roles: Role[]) {
  const ids = new Set(roles.map((role) => role.id));
  selectedRoleIds.value = selectedRoleIds.value.filter((id) => !ids.has(id));
}

async function save() {
  if (!displayName.value.trim() || saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    const basePayload = {
      max_consecutive_performances: maxConsecutive.value,
      rating_level: ratingLevel.value,
      low_rating_monthly_cap: monthlyCap.value,
      notes: notes.value.trim() || null,
    };
    let actorId = props.actor?.id ?? createdActorId.value;
    if (!actorId) {
      const result = await adminApi.createActor(props.token, {
        display_name: displayName.value.trim(), phone_number: phoneNumber.value.trim(),
        theater_ids: theaterIds.value, entry_theater_id: entryTheaterId.value, ...basePayload,
      });
      const created = "actor" in result ? result.actor : result as unknown as Actor;
      actorId = created.id;
      createdActorId.value = created.id;
      if ("credential_delivery" in result) credentialDelivery.value = result.credential_delivery;
    } else if (props.actor) {
      await adminApi.updateActor(props.token, actorId, {
        phone_number: phoneNumber.value.trim(), theater_ids: theaterIds.value,
        entry_theater_id: entryTheaterId.value, ...basePayload,
      });
    }
    await adminApi.replaceActorCapabilities(props.token, actorId, selectedRoleIds.value);
    emit("saved");
    emit("update:modelValue", false);
    if (credentialDelivery.value) credentialOpen.value = true;
  } catch (error: any) {
    saveError.value = error?.message || "保存演员失败";
    emit("error", saveError.value);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.drawer-error { margin-bottom: 18px; }
.actor-form { display: grid; gap: 22px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.wide-field { grid-column: 1 / -1; }
.form-grid :deep(.el-select), .form-grid :deep(.el-input-number) { width: 100%; }
.capability-section { border-top: 1px solid #eaecf0; padding-top: 20px; }
.membership-section { border-top: 1px solid #eaecf0; padding-top: 20px; }
.theater-options { display: flex; flex-wrap: wrap; gap: 8px; }.theater-options :deep(.el-checkbox) { margin: 0; }
.section-title { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.section-title span { color: var(--text-secondary); font-size: 13px; }
.theater-role-group { padding: 14px; border: 1px solid #e4e9f1; border-radius: 10px; background: #fafbfc; }
.theater-role-group + .theater-role-group { margin-top: 12px; }
.group-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.role-options { display: flex; flex-wrap: wrap; gap: 8px; }
.role-options :deep(.el-checkbox) { margin: 0; }
@media (max-width: 640px) { .form-grid { grid-template-columns: 1fr; }.wide-field { grid-column: auto; } }
</style>
