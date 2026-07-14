<template>
  <div class="panel" style="margin: 0;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h3>导入明细表</h3>
      <button
        v-if="!isBatchReadOnly"
        type="button"
        @click="$emit('addManual')"
        style="padding: 6px 12px; border-radius: 6px; background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.25); color: var(--text-primary); font-size: 13px; cursor: pointer;"
      >
        手动添加条目
      </button>
    </div>

    <div style="overflow-x: auto;">
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
        <thead>
          <tr style="border-bottom: 1px solid var(--panel-border); color: var(--text-secondary);">
            <th style="padding: 8px; width: 90px;">类型</th>
            <th style="padding: 8px; width: 100px;">玩家</th>
            <th style="padding: 8px; width: 100px;">原始演员</th>
            <th style="padding: 8px; width: 100px;">原始角色</th>
            <th style="padding: 8px; width: 120px;">匹配演员</th>
            <th style="padding: 8px; width: 120px;">匹配角色</th>
            <th style="padding: 8px; width: 150px;">匹配场次</th>
            <th style="padding: 8px; width: 120px;">备注</th>
            <th style="padding: 8px; width: 100px;">校验状态</th>
            <th style="padding: 8px; width: 110px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <ImportItemEditor
            v-for="item in draft.items"
            :key="item.id"
            :item="item"
            :actors="actors"
            :roles="roles"
            :performances="performances"
            :isConfirmed="item.confirmed_at !== null"
            :isBatchReadOnly="isBatchReadOnly"
            @save="$emit('saveItem', item.id, $event)"
            @confirm="$emit('confirmItem', item.id)"
          />
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ImportDraft, Actor, Role, Performance } from "../../api/admin";
import ImportItemEditor from "./ImportItemEditor.vue";

defineProps<{
  draft: ImportDraft;
  actors: Actor[];
  roles: Role[];
  performances: Performance[];
  isBatchReadOnly: boolean;
}>();

defineEmits<{
  (e: "addManual"): void;
  (e: "saveItem", id: number, fields: any): void;
  (e: "confirmItem", id: number): void;
}>();
</script>
