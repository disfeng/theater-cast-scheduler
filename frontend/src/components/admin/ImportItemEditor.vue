<template>
  <tr style="border-bottom: 1px solid var(--panel-border);">
    <td style="padding: 8px;">
      <select
        aria-label="类型"
        v-model="fields.item_kind"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
      >
        <option value="wish">许愿</option>
        <option value="designation">指定</option>
      </select>
    </td>
    <td style="padding: 8px;">
      <input
        aria-label="玩家"
        type="text"
        v-model="fields.player_name"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
      />
    </td>
    <td style="padding: 8px;">
      <input
        aria-label="原始演员"
        type="text"
        v-model="fields.actor_name_raw"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
      />
    </td>
    <td style="padding: 8px;">
      <input
        aria-label="原始角色"
        type="text"
        v-model="fields.role_name_raw"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
      />
    </td>
    <td style="padding: 8px;">
      <select
        aria-label="匹配演员"
        v-model="fields.actor_id"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
      >
        <option :value="null">-- 未选择 --</option>
        <option v-for="act in actors" :key="act.id" :value="act.id">
          {{ act.display_name }}
        </option>
      </select>
    </td>
    <td style="padding: 8px;">
      <select
        aria-label="匹配角色"
        v-model="fields.role_id"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
      >
        <option :value="null">-- 未选择 --</option>
        <option v-for="rl in roles" :key="rl.id" :value="rl.id">
          {{ rl.name }}
        </option>
      </select>
    </td>
    <td style="padding: 8px;">
      <select
        v-if="fields.item_kind === 'designation'"
        aria-label="匹配场次"
        v-model="fields.target_performance_id"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(0, 0, 0, 0.8); border: 1px solid var(--panel-border); color: #fff;"
      >
        <option :value="null">-- 全周或未指定 --</option>
        <option v-for="perf in performances" :key="perf.id" :value="perf.id">
          {{ perf.performance_date }} ({{ perf.slot === 'early' ? '下午场' : perf.slot === 'late' ? '晚场' : perf.slot }})
        </option>
      </select>
      <span v-else style="color: var(--text-secondary); font-size: 13px;">—</span>
    </td>
    <td style="padding: 8px;">
      <input
        aria-label="备注"
        type="text"
        v-model="fields.note"
        :disabled="isConfirmed || isBatchReadOnly"
        style="width: 100%; padding: 6px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--panel-border); color: #fff;"
      />
    </td>
    <td style="padding: 8px;">
      <span v-if="isConfirmed" style="color: #0f9d58; font-weight: bold;">已确认</span>
      <span v-else-if="item.validation_status === 'valid'" style="color: #0f9d58;">有效</span>
      <span v-else style="color: #d9383a;" :title="item.failure_reason || '解析失败'">
        无效 ({{ formatFailureReason(item.failure_reason) }})
      </span>
    </td>
    <td style="padding: 8px;">
      <div v-if="!isConfirmed && !isBatchReadOnly" style="display: flex; gap: 6px;">
        <button
          type="button"
          @click="handleSave"
          style="padding: 4px 8px; background: #1a73e8; color: white; border: 0; border-radius: 4px; cursor: pointer;"
        >
          保存
        </button>
        <button
          v-if="item.validation_status === 'valid'"
          type="button"
          @click="handleConfirm"
          style="padding: 4px 8px; background: #0f9d58; color: white; border: 0; border-radius: 4px; cursor: pointer;"
        >
          确认
        </button>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ImportDraftItem, Actor, Role, Performance } from "../../api/admin";

const props = defineProps<{
  item: ImportDraftItem;
  actors: Actor[];
  roles: Role[];
  performances: Performance[];
  isConfirmed: boolean;
  isBatchReadOnly: boolean;
}>();

const emit = defineEmits<{
  (e: "save", fields: any): void;
  (e: "confirm"): void;
}>();

const fields = ref({
  item_kind: props.item.item_kind,
  player_name: props.item.player_name || "",
  actor_name_raw: props.item.actor_name_raw || "",
  role_name_raw: props.item.role_name_raw || "",
  actor_id: props.item.actor_id,
  role_id: props.item.role_id,
  target_performance_id: props.item.target_performance_id,
  note: props.item.note || "",
});

watch(() => props.item, (newItem) => {
  fields.value = {
    item_kind: newItem.item_kind,
    player_name: newItem.player_name || "",
    actor_name_raw: newItem.actor_name_raw || "",
    role_name_raw: newItem.role_name_raw || "",
    actor_id: newItem.actor_id,
    role_id: newItem.role_id,
    target_performance_id: newItem.target_performance_id,
    note: newItem.note || "",
  };
}, { deep: true });

const handleSave = () => {
  emit("save", { ...fields.value });
};

const handleConfirm = () => {
  emit("confirm");
};

const formatFailureReason = (reason: string | null): string => {
  const labels: Record<string, string> = {
    actor_not_found: "未找到演员",
    role_not_found: "未找到角色",
    actor_role_capability_missing: "演员不能出演该角色",
    performance_outside_batch: "场次不在当前批次",
    player_name_required: "请填写玩家名称",
    designation_type_required: "请选择指定类型",
  };
  if (!reason) return "格式或匹配错误";
  return `${labels[reason] ?? "校验失败"} [${reason}]`;
};
</script>
