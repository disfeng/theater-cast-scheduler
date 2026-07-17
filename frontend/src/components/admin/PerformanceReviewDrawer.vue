<template>
  <el-drawer :model-value="modelValue" size="min(720px, 92vw)" destroy-on-close @close="$emit('update:modelValue', false)">
    <template #header>
      <div v-if="workspace" class="drawer-title">
        <h2>{{ monthDay(workspace.performance.performance_date) }} · {{ workspace.performance.slot_name }}</h2>
        <span>{{ workspace.performance.theater_name }} · {{ shortTime(workspace.performance.start_time) }}</span>
      </div>
      <el-skeleton v-else :rows="1" animated />
    </template>
    <div v-loading="loading">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <template v-if="workspace">
        <div v-if="workspace.conflicts.length" class="conflicts">
          <el-alert v-for="conflict in workspace.conflicts" :key="`${conflict.designation_id}-${conflict.code}`" :title="conflict.message" :type="conflict.severity === 'hard' ? 'error' : 'warning'" :closable="false" show-icon />
        </div>
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="`玩家 (${workspace.players.length})`" name="players">
            <div class="review-list">
              <article v-for="player in workspace.players" :key="player.id" class="review-row">
                <div><strong>{{ player.player_name }}</strong><p>{{ player.role_name || '未登记对位角色' }}</p></div>
                <span>{{ visitLabel(player) }}</span>
              </article>
              <el-empty v-if="!workspace.players.length" description="暂无玩家登记" :image-size="72" />
            </div>
          </el-tab-pane>
          <el-tab-pane label="场次信息板" name="board" lazy>
            <PerformanceBoardReview :performance-id="workspace.performance.id" @changed="$emit('changed')" />
          </el-tab-pane>
          <el-tab-pane :label="`指定 (${workspace.designations.length})`" name="designations">
            <PerformanceDesignationReview :rows="workspace.designations" @changed="$emit('changed')" @reject="id => startReject('designation', id)" />
          </el-tab-pane>
          <el-tab-pane :label="`许愿 (${workspace.wishes.length})`" name="wishes">
            <el-empty v-if="!workspace.wishes.length" description="暂无许愿" :image-size="72" />
            <article v-for="row in workspace.wishes" :key="row.id" class="review-row wish-row">
              <div class="wish-identity"><span class="wish-badge">许愿</span><div><strong>{{ row.player_name }}</strong><p>{{ row.actor_name }} / {{ row.role_name }}</p></div></div>
              <div class="row-actions">
                <span class="wish-status" :class="`status-${row.status}`">{{ wishStatusLabel(row.status) }}</span>
                <div v-if="row.status === 'active'" class="action-group"><el-button type="success" plain size="small" @click="$emit('accept-wish', row.id)">接受</el-button><el-button text type="danger" size="small" :aria-label="`拒绝许愿 ${row.player_name}`" @click="startReject('wish', row.id)">拒绝</el-button></div>
              </div>
            </article>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
    <el-dialog v-model="rejectVisible" title="填写拒绝原因" width="460px" append-to-body>
      <el-input v-model="rejectReason" type="textarea" :rows="4" aria-label="拒绝原因" placeholder="请说明拒绝原因，便于客服回复和事后核对" />
      <template #footer><el-button @click="rejectVisible = false">取消</el-button><el-button type="danger" :disabled="!rejectReason.trim()" @click="confirmReject">确认拒绝</el-button></template>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import type { PerformanceWorkspace } from "../../features/designation-workspace/types";
import PerformanceBoardReview from "./PerformanceBoardReview.vue";
import PerformanceDesignationReview from "./PerformanceDesignationReview.vue";
const props = withDefaults(defineProps<{ modelValue: boolean; workspace: PerformanceWorkspace | null; loading: boolean; error: string | null; initialTab?: string }>(), { initialTab: "players" });
const emit = defineEmits<{ "update:modelValue": [value: boolean]; "reject-designation": [id: number, reason: string]; "reject-wish": [id: number, reason: string]; "accept-wish": [id: number]; changed: []; "tab-change": [value: string] }>();
const activeTab = ref("players");
watch(() => props.initialTab, value => { if (["players", "board", "designations", "wishes"].includes(value)) activeTab.value = value; }, { immediate: true });
watch(activeTab, value => emit("tab-change", value));
const rejectVisible = ref(false);
const rejectReason = ref("");
const rejectTarget = ref<{ kind: "designation" | "wish"; id: number } | null>(null);
const startReject = (kind: "designation" | "wish", id: number) => { rejectTarget.value = { kind, id }; rejectReason.value = ""; rejectVisible.value = true; };
const confirmReject = () => {
  if (!rejectTarget.value || !rejectReason.value.trim()) return;
  const reason = rejectReason.value.trim();
  if (rejectTarget.value.kind === "designation") {
    emit("reject-designation", rejectTarget.value.id, reason);
  } else {
    emit("reject-wish", rejectTarget.value.id, reason);
  }
  rejectVisible.value = false;
};
const monthDay = (value: string) => { const [, month, day] = value.split("-"); return `${Number(month)}月${Number(day)}日`; };
const shortTime = (value: string) => value.slice(0, 5);
const visitLabel = (player: PerformanceWorkspace["players"][number]) => [player.theater_visit_count != null ? `${player.theater_visit_count} 刷剧场` : null, player.role_visit_count != null ? `${player.role_visit_count} 刷角色` : null].filter(Boolean).join(" · ") || "未登记刷数";
const wishStatusLabel = (value: string | null) => ({ active: "待处理", accepted: "已接受", cancelled: "已拒绝", fulfilled: "已完成" }[value || ""] || value || "待处理");
</script>

<style scoped>
.drawer-title h2{margin:0 0 5px;color:#172033}.drawer-title span,.review-row p,.review-row>span{color:#748096}.conflicts{display:grid;gap:8px;margin-bottom:16px}.review-list{display:grid;gap:10px}.review-row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:14px 16px;border:1px solid #e3e8f0;border-radius:10px;background:#fff}.review-row p{margin:5px 0 0;font-size:13px}.wish-row{transition:border-color .2s,box-shadow .2s}.wish-row+.wish-row{margin-top:10px}.wish-row:hover{border-color:#d4dce8;box-shadow:0 4px 14px rgb(15 23 42 / 5%)}.wish-identity,.row-actions,.action-group{display:flex;align-items:center}.wish-identity{min-width:0;gap:12px}.wish-badge{padding:4px 9px;border-radius:999px;background:#fff7e6;color:#a85b00;font-size:13px;font-weight:700}.row-actions{gap:12px}.action-group{gap:4px}.action-group .el-button{margin-left:0}.wish-status{display:inline-flex;align-items:center;gap:6px;color:#64748b;font-size:13px;font-weight:600}.wish-status::before{width:7px;height:7px;border-radius:50%;background:#f0a020;content:""}.status-accepted,.status-fulfilled{color:#16865b}.status-accepted::before,.status-fulfilled::before{background:#22a06b}.status-cancelled{color:#dc2626}.status-cancelled::before{background:#ef4444}@media(max-width:560px){.review-row{align-items:flex-start;flex-direction:column}.row-actions{width:100%;justify-content:space-between}}
</style>
