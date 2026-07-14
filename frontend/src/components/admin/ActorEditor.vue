<template>
  <div style="border: 1px solid var(--panel-border); padding: 20px; border-radius: 12px; background: rgba(255, 255, 255, 0.01);">
    <h4 style="margin-bottom: 16px; color: #fff;">{{ actor.display_name }}</h4>
    <div style="display: grid; gap: 16px; grid-template-columns: 1fr 1fr; margin-bottom: 16px;">
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label :for="'edit-max-consecutive-' + actor.id">修改最大连场</label>
        <input
          :id="'edit-max-consecutive-' + actor.id"
          aria-label="修改最大连场"
          type="number"
          min="1"
          max="3"
          v-model.number="maxConsecutive"
          style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
        />
      </div>
      
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label :for="'edit-rating-' + actor.id">评级</label>
        <select
          :id="'edit-rating-' + actor.id"
          v-model="ratingLevel"
          style="padding: 8px 12px; border-radius: 6px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
        >
          <option value="high">高</option>
          <option value="normal">普通</option>
          <option value="low">低</option>
          <option value="suspended">暂停</option>
        </select>
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label :for="'edit-monthly-cap-' + actor.id">低评级上限</label>
        <input
          :id="'edit-monthly-cap-' + actor.id"
          type="number"
          min="0"
          v-model.number="monthlyCap"
          style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
        />
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px;">
        <label :for="'edit-notes-' + actor.id">备注</label>
        <input
          :id="'edit-notes-' + actor.id"
          v-model="notes"
          style="padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
        />
      </div>
    </div>

    <div style="margin-bottom: 20px;">
      <h5 style="margin-bottom: 8px; color: var(--text-secondary);">可出演角色：</h5>
      <div style="display: flex; gap: 16px; flex-wrap: wrap;">
        <label
          v-for="role in roles"
          :key="role.id"
          style="display: flex; align-items: center; gap: 6px; cursor: pointer;"
        >
          <input
            type="checkbox"
            :aria-label="role.name"
            :checked="selectedRoleIds.includes(role.id)"
            @change="handleToggleRole(role.id)"
            style="width: 16px; height: 16px;"
          />
          {{ role.name }}
        </label>
      </div>
    </div>

    <button
      type="button"
      @click="handleSave"
      style="padding: 8px 16px; border-radius: 6px; background: var(--primary); color: #fff; border: none; font-weight: 600; cursor: pointer;"
    >
      保存演员设置
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { Actor, Role, adminApi } from "../../api/admin";

const props = defineProps<{
  actor: Actor;
  roles: Role[];
  token: string;
}>();

const emit = defineEmits<{
  (e: "refresh"): void;
  (e: "error", msg: string | null): void;
}>();

const maxConsecutive = ref(props.actor.max_consecutive_performances);
const ratingLevel = ref(props.actor.rating_level);
const monthlyCap = ref<number | null>(props.actor.low_rating_monthly_cap);
const notes = ref(props.actor.notes || "");
const selectedRoleIds = ref<number[]>(props.actor.role_ids || []);

watch(() => props.actor, (newActor) => {
  maxConsecutive.value = newActor.max_consecutive_performances;
  ratingLevel.value = newActor.rating_level;
  monthlyCap.value = newActor.low_rating_monthly_cap;
  notes.value = newActor.notes || "";
  selectedRoleIds.value = newActor.role_ids || [];
}, { deep: true });

const handleToggleRole = (roleId: number) => {
  if (selectedRoleIds.value.includes(roleId)) {
    selectedRoleIds.value = selectedRoleIds.value.filter((id) => id !== roleId);
  } else {
    selectedRoleIds.value = [...selectedRoleIds.value, roleId];
  }
};

const handleSave = async () => {
  emit("error", null);
  try {
    await adminApi.updateActor(props.token, props.actor.id, {
      max_consecutive_performances: maxConsecutive.value,
      rating_level: ratingLevel.value,
      low_rating_monthly_cap: monthlyCap.value || null,
      notes: notes.value || null,
    });
    await adminApi.replaceActorCapabilities(props.token, props.actor.id, selectedRoleIds.value);
    emit("refresh");
  } catch (err: any) {
    emit("error", err.message || "更新演员失败");
  }
};
</script>
